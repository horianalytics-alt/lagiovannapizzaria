import os

import pytest

from lagiovanna import create_app
from lagiovanna.db import abrir, apagar_tudo


@pytest.fixture()
def app(tmp_path):
    """SQLite por padrão; com TESTE_POSTGRES_URL definido, roda os mesmos testes num Postgres (que é zerado)."""
    url = os.environ.get("TESTE_POSTGRES_URL")
    if url:
        db = abrir("postgres", url)
        apagar_tudo(db)
    app = create_app(tmp_path, url_banco=url)
    app.config["TESTING"] = True
    return app


def entrar(app, usuario, senha):
    cliente = app.test_client()
    resposta = cliente.post("/api/login", json={"usuario": usuario, "senha": senha})
    assert resposta.status_code == 200, resposta.json
    return cliente


def produto(cardapio, nome):
    for categoria in cardapio["categorias"]:
        for item in categoria["produtos"]:
            if item["nome"] == nome:
                return item
    raise AssertionError(nome)


def test_fluxo_completo_da_mesa_ao_caixa(app):
    publico = app.test_client()
    cozinha = entrar(app, "cozinha", "cozinha123")
    garcom = entrar(app, "garcom", "garcom123")
    admin = entrar(app, "admin", "giovanna123")

    antes = admin.get("/api/admin/indicadores").json
    cardapio = publico.get("/api/cardapio").json
    calabresa, parma = produto(cardapio, "Calabresa"), produto(cardapio, "Parma com rúcula")
    coca = produto(cardapio, "Coca-Cola lata 350 ml")
    borda = cardapio["bordas"][0]

    # Cliente monta uma meio a meio com borda e duas bebidas na mesa 2 (livre).
    assert publico.get("/api/mesa/2").json["status"] == "livre"
    resposta = publico.post("/api/mesa/2/pedidos", json={"itens": [
        {"produto_id": calabresa["id"], "produto2_id": parma["id"], "borda_id": borda["id"],
         "quantidade": 1, "observacao": "  Sem   cebola "},
        {"produto_id": coca["id"], "quantidade": 2},
    ]})
    assert resposta.status_code == 201
    pedido_id = resposta.json["pedido_id"]
    esperado = max(calabresa["preco"], parma["preco"]) + borda["preco"] + 2 * coca["preco"]

    mesa = publico.get("/api/mesa/2").json
    assert mesa["status"] == "ocupada" and mesa["subtotal"] == esperado
    item = mesa["pedidos"][0]["itens"][0]
    assert item["descricao"] == "½ Calabresa + ½ Parma com rúcula"
    assert item["detalhe"] == f"Borda {borda['nome']}" and item["observacao"] == "Sem cebola"

    # Aparece na cozinha, que avança o status.
    fila = cozinha.get("/api/cozinha/pedidos").json
    ticket = next(p for p in fila if p["id"] == pedido_id)
    assert ticket["mesa"] == 2 and ticket["status"] == "pendente"
    for status in ("preparo", "pronto"):
        assert cozinha.post(f"/api/pedidos/{pedido_id}/status", json={"status": status}).status_code == 200
    assert cozinha.post(f"/api/pedidos/{pedido_id}/status", json={"status": "entregue"}).status_code == 403

    # Garçom vê o pedido pronto, entrega e lança mais um item.
    mesa_garcom = next(m for m in garcom.get("/api/mesas").json if m["numero"] == 2)
    assert mesa_garcom["pedidos_prontos"] == 1
    assert garcom.post(f"/api/pedidos/{pedido_id}/status", json={"status": "entregue"}).status_code == 200
    assert garcom.post(f"/api/mesas/{mesa_garcom['id']}/pedidos",
                       json={"itens": [{"produto_id": coca["id"], "quantidade": 1}]}).status_code == 201
    esperado += coca["preco"]

    # Cliente pede a conta; garçom atende.
    assert publico.post("/api/mesa/2/chamar", json={"tipo": "conta"}).status_code == 200
    assert publico.get("/api/mesa/2").json["status"] == "aguardando"
    assert garcom.post(f"/api/mesas/{mesa_garcom['id']}/atender").status_code == 200

    # Caixa: pagamento errado é recusado; com 10% e desconto fecha e libera a mesa.
    url = f"/api/admin/mesas/{mesa_garcom['id']}/fechar"
    assert garcom.post(url, json={}).status_code == 403
    taxa = round(esperado * 0.10)
    total = esperado - 500 + taxa
    errado = admin.post(url, json={"desconto": 500, "taxa_servico_pct": 10,
                                   "pagamentos": [{"forma": "pix", "valor": total - 1}]})
    assert errado.status_code == 400 and "somam" in errado.json["erro"]
    certo = admin.post(url, json={"desconto": 500, "taxa_servico_pct": 10, "pagamentos": [
        {"forma": "pix", "valor": total - 2000}, {"forma": "dinheiro", "valor": 2000}]})
    assert certo.status_code == 200 and certo.json["total"] == total
    assert publico.get("/api/mesa/2").json["status"] == "livre"

    # Indicadores refletem a venda.
    depois = admin.get("/api/admin/indicadores").json
    assert depois["faturamento"] == antes["faturamento"] + total
    assert depois["contas_fechadas"] == antes["contas_fechadas"] + 1
    assert depois["pedidos"] == antes["pedidos"] + 2
    assert depois["ticket_medio"] == round(depois["faturamento"] / depois["contas_fechadas"])

    def qtd(dados, nome):
        return next((r["quantidade"] for r in dados["ranking_pizzas"] if r["nome"] == nome), 0)

    assert qtd(depois, "Calabresa") == qtd(antes, "Calabresa") + 0.5
    assert admin.get("/api/admin/contas").json[0]["total"] == total


def test_acesso_por_perfil(app):
    anonimo = app.test_client()
    assert anonimo.get("/api/mesas").status_code == 401
    assert anonimo.get("/admin").status_code == 302
    assert anonimo.post("/api/login", json={"usuario": "admin", "senha": "errada"}).status_code == 401
    cozinha = entrar(app, "cozinha", "cozinha123")
    assert cozinha.get("/api/admin/indicadores").status_code == 403
    assert cozinha.get("/api/mesas").status_code == 403
    assert cozinha.get("/admin").headers["Location"] == "/cozinha"
    garcom = entrar(app, "garcom", "garcom123")
    assert garcom.get("/api/cozinha/pedidos").status_code == 403
    assert garcom.get("/garcom").status_code == 200
    assert anonimo.get("/mesa/5").status_code == 200
    assert anonimo.get("/mesa/99").status_code == 404


def test_cardapio_pausar_editar_excluir(app):
    publico = app.test_client()
    admin = entrar(app, "admin", "giovanna123")
    dados = admin.get("/api/admin/cardapio").json
    categoria = dados["categorias"][0]
    mussarela = next(p for p in dados["produtos"] if p["nome"] == "Mussarela")

    # Pausar tira do cardápio do cliente e bloqueia o pedido.
    assert admin.post(f"/api/admin/produtos/{mussarela['id']}/ativo", json={"ativo": False}).status_code == 200
    nomes = [p["nome"] for c in publico.get("/api/cardapio").json["categorias"] for p in c["produtos"]]
    assert "Mussarela" not in nomes
    recusado = publico.post("/api/mesa/1/pedidos", json={"itens": [{"produto_id": mussarela["id"], "quantidade": 1}]})
    assert recusado.status_code == 409

    novo = admin.post("/api/admin/produtos", json={
        "categoria_id": categoria["id"], "nome": "Teste da casa", "descricao": "x", "preco": 4500})
    assert novo.status_code == 201
    novo_id = novo.json["id"]
    assert admin.put(f"/api/admin/produtos/{novo_id}", json={
        "categoria_id": categoria["id"], "nome": "Teste editado", "descricao": "", "preco": 4700}).status_code == 200
    item = produto(publico.get("/api/cardapio").json, "Teste editado")
    assert item["preco"] == 4700
    assert admin.delete(f"/api/admin/produtos/{novo_id}").status_code == 200
    nomes = [p["nome"] for c in publico.get("/api/cardapio").json["categorias"] for p in c["produtos"]]
    assert "Teste editado" not in nomes

    assert admin.delete(f"/api/admin/categorias/{categoria['id']}").status_code == 409
    vazia = admin.post("/api/admin/categorias", json={"nome": "Calzones", "tipo": "outro"}).json["id"]
    assert admin.delete(f"/api/admin/categorias/{vazia}").status_code == 200

    borda = admin.post("/api/admin/bordas", json={"nome": "Doce de leite", "preco": 1200})
    assert borda.status_code == 201
    assert any(b["nome"] == "Doce de leite" for b in publico.get("/api/cardapio").json["bordas"])
    assert admin.delete(f"/api/admin/bordas/{borda.json['id']}").status_code == 200


def test_mesas_qrcode_e_equipe(app):
    admin = entrar(app, "admin", "giovanna123")
    assert admin.post("/api/admin/mesas", json={"numero": 5}).status_code == 409
    assert admin.post("/api/admin/mesas", json={"numero": 20}).status_code == 201
    assert admin.put("/api/admin/config/url_base", json={"url_base": "http://192.168.0.10:5000/"}).status_code == 200
    dados = admin.get("/api/admin/mesas").json
    mesa20 = next(m for m in dados["mesas"] if m["numero"] == 20)
    assert mesa20["link"] == "http://192.168.0.10:5000/mesa/20"
    svg = admin.get(f"/api/admin/mesas/{mesa20['id']}/qr.svg")
    assert svg.status_code == 200 and b"<svg" in svg.data
    assert "Mesa 20" in admin.get("/admin/qrcodes").get_data(as_text=True)
    assert admin.delete(f"/api/admin/mesas/{mesa20['id']}").status_code == 200
    ocupada = next(m for m in admin.get("/api/mesas").json if m["status"] != "livre")
    assert admin.delete(f"/api/admin/mesas/{ocupada['id']}").status_code == 409

    assert admin.post("/api/admin/usuarios", json={
        "nome": "Bia", "usuario": "bia", "senha": "segredo1", "perfil": "garcom"}).status_code == 201
    bia = entrar(app, "bia", "segredo1")
    assert bia.get("/api/mesas").status_code == 200
    bia_id = next(u["id"] for u in admin.get("/api/admin/usuarios").json if u["usuario"] == "bia")
    assert admin.put(f"/api/admin/usuarios/{bia_id}", json={"nome": "Bia", "perfil": "garcom", "ativo": False}).status_code == 200
    assert bia.get("/api/mesas").status_code == 401
    eu = admin.get("/api/eu").json
    assert admin.put(f"/api/admin/usuarios/{eu['id']}", json={"nome": "X", "perfil": "garcom"}).status_code == 409


def test_painel_abre_com_dados_de_demonstracao(app):
    admin = entrar(app, "admin", "giovanna123")
    dados = admin.get("/api/admin/indicadores").json
    assert dados["faturamento"] > 0 and dados["contas_fechadas"] == 14 and dados["ranking_pizzas"]
    assert dados["mesas_abertas"] == 4 and len(dados["ultimos_dias"]) == 7
    assert all(d["valor"] > 0 for d in dados["ultimos_dias"])


def test_versoes_avisam_as_telas_e_foto_fica_no_banco(app):
    publico = app.test_client()
    admin = entrar(app, "admin", "giovanna123")
    resposta = publico.get("/api/versao")
    assert "s-maxage=2" in resposta.headers["Cache-Control"] and "Set-Cookie" not in resposta.headers
    antes = resposta.json["versoes"]
    assert publico.post("/api/mesa/1/pedidos", json={"itens": [{"produto_id": 1, "quantidade": 1}]}).status_code == 201
    depois = publico.get("/api/versao").json["versoes"]
    assert depois["pedidos"] == antes["pedidos"] + 1 and depois["cardapio"] == antes["cardapio"]

    import io
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    envio = admin.post("/api/admin/upload", data={"imagem": (io.BytesIO(png), "foto.png")})
    assert envio.status_code == 201
    foto = publico.get(envio.json["url"])
    assert foto.status_code == 200 and foto.data == png and foto.mimetype == "image/png"
    assert "immutable" in foto.headers["Cache-Control"]
    assert admin.post("/api/admin/upload", data={"imagem": (io.BytesIO(b"oi"), "foto.png")}).status_code == 400


def test_zerar_vendas_mantem_cardapio_e_equipe(app):
    admin = entrar(app, "admin", "giovanna123")
    assert admin.post("/api/admin/zerar-vendas", json={}).status_code == 400
    assert admin.post("/api/admin/zerar-vendas", json={"confirmacao": "ZERAR"}).status_code == 200
    dados = admin.get("/api/admin/indicadores").json
    assert dados["faturamento"] == 0 and dados["pedidos"] == 0 and dados["mesas_abertas"] == 0
    assert all(m["status"] == "livre" for m in admin.get("/api/mesas").json)
    assert len(admin.get("/api/admin/cardapio").json["produtos"]) == 34
