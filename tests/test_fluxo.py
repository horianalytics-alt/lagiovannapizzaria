import os
import re

import pytest
from flask.testing import FlaskClient

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
    app.test_client_class = ClienteComCodigo
    return app


def codigo_da_mesa(app, numero):
    with app.app_context():
        from lagiovanna.db import get_db

        return get_db().execute("SELECT codigo FROM mesas WHERE numero = ?", (numero,)).fetchone()[0]


class ClienteComCodigo(FlaskClient):
    """Como o celular que leu o QR Code: manda o código da mesa nas rotas do cliente, salvo se o teste der outro."""

    def open(self, *args, **kwargs):
        caminho = args[0] if args and isinstance(args[0], str) else kwargs.get("path", "")
        achou = re.match(r"/api/mesa/(\d+)", caminho)
        if achou:
            cabecalhos = dict(kwargs.pop("headers", None) or {})
            cabecalhos.setdefault("X-Codigo-Mesa", codigo_da_mesa(self.application, int(achou.group(1))))
            kwargs["headers"] = cabecalhos
        return super().open(*args, **kwargs)


def entrar(app, usuario, senha):
    """Entra e, se a senha for provisória (como as do seed), define uma nova: senha + "-Nova1"."""
    cliente = app.test_client()
    resposta = cliente.post("/api/login", json={"usuario": usuario, "senha": senha})
    if resposta.status_code == 401:
        resposta = cliente.post("/api/login", json={"usuario": usuario, "senha": senha + "-Nova1"})
    assert resposta.status_code == 200, resposta.json
    if resposta.json["trocar_senha"]:
        troca = cliente.post("/api/minha-senha", json={"atual": senha, "nova": senha + "-Nova1"})
        assert troca.status_code == 200, troca.json
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
    assert anonimo.get("/mesa?n=5").headers["Location"] == "/mesa/05"
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
    assert mesa20["link"] == f"http://192.168.0.10:5000/mesa/20?c={mesa20['codigo']}"
    svg = admin.get(f"/api/admin/mesas/{mesa20['id']}/qr.svg")
    assert svg.status_code == 200 and b"<svg" in svg.data
    assert "Mesa 20" in admin.get("/admin/qrcodes").get_data(as_text=True)
    assert admin.delete(f"/api/admin/mesas/{mesa20['id']}").status_code == 200
    ocupada = next(m for m in admin.get("/api/mesas").json if m["status"] != "livre")
    assert admin.delete(f"/api/admin/mesas/{ocupada['id']}").status_code == 409

    assert admin.post("/api/admin/usuarios", json={
        "nome": "Bia", "usuario": "bia", "senha": "segredo-01", "perfil": "garcom"}).status_code == 201
    bia = entrar(app, "bia", "segredo-01")
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


def test_senha_provisoria_bloqueia_ate_trocar_e_sessao_antiga_cai(app):
    admin = app.test_client()
    login = admin.post("/api/login", json={"usuario": "admin", "senha": "giovanna123"})
    assert login.json["trocar_senha"] is True
    bloqueio = admin.get("/api/admin/indicadores")
    assert bloqueio.status_code == 403 and bloqueio.json["trocar_senha"] is True
    assert admin.get("/admin").headers["Location"] == "/trocar-senha"
    assert admin.post("/api/minha-senha", json={"atual": "errada", "nova": "Outra-senha-9"}).status_code == 400
    assert admin.post("/api/minha-senha", json={"atual": "giovanna123", "nova": "curta"}).status_code == 400
    assert admin.post("/api/minha-senha", json={"atual": "giovanna123", "nova": "garcom123"}).status_code == 400
    assert admin.post("/api/minha-senha", json={"atual": "giovanna123", "nova": "Outra-senha-9"}).status_code == 200
    assert admin.get("/api/admin/indicadores").status_code == 200

    # Outra sessão aberta com a senha antiga deixa de valer quando a senha muda.
    outro = app.test_client()
    assert outro.post("/api/login", json={"usuario": "admin", "senha": "Outra-senha-9"}).status_code == 200
    assert admin.post("/api/minha-senha", json={"atual": "Outra-senha-9", "nova": "Mais-uma-senha-7"}).status_code == 200
    assert outro.get("/api/admin/indicadores").status_code == 401
    assert admin.get("/api/admin/indicadores").status_code == 200


def test_limite_de_tentativas_de_login(app):
    cliente = app.test_client()
    for _ in range(8):
        assert cliente.post("/api/login", json={"usuario": "garcom", "senha": "errada"}).status_code == 401
    assert cliente.post("/api/login", json={"usuario": "garcom", "senha": "garcom123"}).status_code == 429
    # Outro usuário, do mesmo endereço, ainda consegue entrar.
    assert cliente.post("/api/login", json={"usuario": "cozinha", "senha": "cozinha123"}).status_code == 200


def test_protecoes_das_paginas_e_das_rotas_abertas(app):
    publico = app.test_client()
    pagina = publico.get("/mesa/5")
    politica = pagina.headers["Content-Security-Policy"]
    assert "script-src 'self'" in politica and "unsafe-inline" not in politica
    assert pagina.headers["Referrer-Policy"] == "same-origin" and pagina.headers["Cache-Control"] == "no-store"
    html = pagina.get_data(as_text=True)
    assert "<script>" not in html and "onclick" not in html and "onsubmit" not in publico.get("/").get_data(as_text=True)

    # Alteração vinda de outro site é recusada.
    de_fora = publico.post("/api/mesa/1/chamar", json={"tipo": "garcom"}, headers={"Origin": "https://outro-site.example"})
    assert de_fora.status_code == 403

    # Limite de pedidos pelo QR Code por mesa.
    item = {"itens": [{"produto_id": 1, "quantidade": 1}]}
    codigos = [publico.post("/api/mesa/12/pedidos", json=item).status_code for _ in range(11)]
    assert codigos == [201] * 10 + [429]

    # Chamado repetido não gera novo aviso para o salão.
    publico.post("/api/mesa/1/chamar", json={"tipo": "garcom"})
    antes = publico.get("/api/versao").json["versoes"]["mesas"]
    publico.post("/api/mesa/1/chamar", json={"tipo": "garcom"})
    assert publico.get("/api/versao").json["versoes"]["mesas"] == antes


def test_privacidade_aviso_e_exclusao_de_integrante(app):
    publico = app.test_client()
    admin = entrar(app, "admin", "giovanna123")
    assert admin.put("/api/admin/privacidade", json={
        "empresa_nome": "La Giovanna Ltda.", "empresa_cnpj": "12.345.678/0001-90",
        "empresa_contato": "privacidade@exemplo.com"}).status_code == 200
    aviso = publico.get("/privacidade").get_data(as_text=True)
    assert "La Giovanna Ltda." in aviso and "12.345.678/0001-90" in aviso and "privacidade@exemplo.com" in aviso

    garcom = entrar(app, "garcom", "garcom123")
    mesa = admin.get("/api/mesas").json[0]
    assert garcom.post(f"/api/mesas/{mesa['id']}/pedidos", json={"itens": [{"produto_id": 1, "quantidade": 1}]}).status_code == 201
    garcom_id = next(u["id"] for u in admin.get("/api/admin/usuarios").json if u["usuario"] == "garcom")
    assert admin.delete(f"/api/admin/usuarios/{garcom_id}").status_code == 200
    assert garcom.get("/api/mesas").status_code == 401
    assert all(u["usuario"] != "garcom" for u in admin.get("/api/admin/usuarios").json)
    pedido = admin.get(f"/api/mesas/{mesa['id']}").json["pedidos"][-1]
    assert pedido["atendente"] == "Ex-integrante da equipe"
    eu = admin.get("/api/eu").json
    assert admin.delete(f"/api/admin/usuarios/{eu['id']}").status_code == 409


def test_codigo_da_mesa_protege_pedidos_e_pode_ser_trocado(app):
    publico = app.test_client()
    admin = entrar(app, "admin", "giovanna123")
    item = {"itens": [{"produto_id": 1, "quantidade": 1}]}
    codigo = codigo_da_mesa(app, 4)
    assert re.fullmatch(r"[A-Z2-9]{10}", codigo) and codigo != codigo_da_mesa(app, 5)

    # Sem código, com código errado ou com o de outra mesa: nada de pedido, chamado ou consumo da mesa.
    for errado in ("", "ERRADO1234", codigo_da_mesa(app, 5)):
        h = {"X-Codigo-Mesa": errado}
        assert publico.post("/api/mesa/4/pedidos", json=item, headers=h).status_code == 403
        assert publico.post("/api/mesa/4/chamar", json={"tipo": "garcom"}, headers=h).status_code == 403
        assert publico.get("/api/mesa/4", headers=h).status_code == 403
    assert publico.post("/api/mesa/4/pedidos", json=item, headers={"X-Codigo-Mesa": codigo.lower()}).status_code == 201

    # A página aberta só com o número mostra o cardápio, sem poder pedir.
    assert '"codigo": null' in publico.get("/mesa/04").get_data(as_text=True)
    assert f'"codigo": "{codigo}"' in publico.get(f"/mesa/04?c={codigo}").get_data(as_text=True)
    assert '"codigo_invalido": true' in publico.get("/mesa/04?c=VELHO12345").get_data(as_text=True)

    # Trocar o código invalida o QR Code antigo.
    mesa4 = next(m for m in admin.get("/api/admin/mesas").json["mesas"] if m["numero"] == 4)
    assert mesa4["link"].endswith(f"/mesa/04?c={codigo}")
    assert admin.post(f"/api/admin/mesas/{mesa4['id']}/novo-codigo").status_code == 200
    novo = codigo_da_mesa(app, 4)
    assert novo != codigo
    assert publico.post("/api/mesa/4/pedidos", json=item, headers={"X-Codigo-Mesa": codigo}).status_code == 403
    assert publico.post("/api/mesa/4/pedidos", json=item, headers={"X-Codigo-Mesa": novo}).status_code == 201
    novo_link = next(m for m in admin.get("/api/admin/mesas").json["mesas"] if m["numero"] == 4)["link"]
    assert novo_link.endswith(f"?c={novo}")
    impressao = admin.get("/admin/qrcodes").get_data(as_text=True)
    assert novo not in impressao and "<svg" in impressao  # o código fica só dentro do QR, não escrito na placa

    # O código não vaza para quem não é gerente.
    garcom = entrar(app, "garcom", "garcom123")
    assert novo not in garcom.get("/api/mesas").get_data(as_text=True)
    assert garcom.post(f"/api/admin/mesas/{mesa4['id']}/novo-codigo").status_code == 403
