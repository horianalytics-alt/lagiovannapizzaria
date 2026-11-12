"""Páginas e API usadas por cliente, garçom e cozinha."""
import hmac
from datetime import timedelta

from flask import Blueprint, Response, abort, g, jsonify, redirect, render_template, request, session

from . import servicos
from .auth import INICIO_POR_PERFIL, exige, pagina_exige
from .db import agora_dt
from .db import agora, get_db
from .eventos import publicar, versoes

MAX_PEDIDOS_POR_MESA = 10  # pedidos feitos pelo QR Code, por mesa, a cada 10 minutos

paginas = Blueprint("paginas", __name__)
api = Blueprint("api", __name__, url_prefix="/api")


# ---------- Páginas ----------

@paginas.get("/")
def inicio():
    return render_template("inicio.html")


@paginas.get("/mesa")
def ir_para_mesa():
    """Recebe o número digitado na página inicial e leva ao cardápio da mesa."""
    numero = request.args.get("n", "")
    if numero.isdigit() and 0 < int(numero) < 1000:
        return redirect(f"/mesa/{int(numero):02d}")
    return redirect("/")


@paginas.get("/privacidade")
def privacidade():
    from .admin import dados_da_empresa

    return render_template("privacidade.html", empresa=dados_da_empresa(get_db()))


@paginas.get("/trocar-senha")
def trocar_senha():
    if g.usuario is None:
        return redirect("/entrar")
    dados = _dados_usuario()
    dados["obrigatoria"] = bool(g.usuario["trocar_senha"])
    return render_template("app.html", modulo="senha", titulo="Trocar senha", tema="claro", dados=dados)


@paginas.get("/entrar")
def entrar():
    if g.usuario is not None:
        return redirect("/trocar-senha" if g.usuario["trocar_senha"] else INICIO_POR_PERFIL[g.usuario["perfil"]])
    return render_template("app.html", modulo="entrar", titulo="Entrar", tema="claro")


@paginas.get("/sair")
def sair():
    session.clear()
    return redirect("/entrar")


@paginas.get("/mesa/<int:numero>")
def mesa(numero):
    mesa = get_db().execute("SELECT codigo FROM mesas WHERE numero = ? AND ativo = 1", (numero,)).fetchone()
    if not mesa:
        return render_template("inicio.html", aviso=f"A mesa {numero:02d} não existe. Confira o número na sua mesa."), 404
    codigo = request.args.get("c", "").strip().upper()
    valido = bool(codigo and mesa["codigo"] and hmac.compare_digest(codigo, mesa["codigo"]))
    dados = {"mesa": numero, "codigo": codigo if valido else None, "codigo_invalido": bool(codigo) and not valido}
    return render_template("app.html", modulo="cliente", titulo=f"Mesa {numero:02d}", tema="claro", dados=dados)


@paginas.get("/garcom")
@pagina_exige("garcom", "admin")
def garcom():
    return render_template("app.html", modulo="garcom", titulo="Garçom", tema="claro", dados=_dados_usuario())


@paginas.get("/cozinha")
@pagina_exige("cozinha", "admin")
def cozinha():
    return render_template("app.html", modulo="cozinha", titulo="Cozinha", tema="escuro", dados=_dados_usuario())


@paginas.get("/admin")
@pagina_exige("admin")
def admin():
    return render_template("app.html", modulo="admin", titulo="Gerência", tema="claro", dados=_dados_usuario())


@paginas.get("/uploads/<path:nome>")
def upload(nome):
    imagem = get_db().execute("SELECT tipo, dados FROM imagens WHERE nome = ?", (nome,)).fetchone()
    if not imagem:
        abort(404)
    resposta = Response(bytes(imagem["dados"]), mimetype=imagem["tipo"])
    # O nome é único por arquivo, então navegador e CDN podem guardar para sempre.
    resposta.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resposta


def _codigo():
    return request.headers.get("X-Codigo-Mesa", "").strip()


def _dados_usuario():
    return {"usuario": {"nome": g.usuario["nome"], "perfil": g.usuario["perfil"]}}


# ---------- API pública (cliente na mesa) ----------

def cardapio_publico(db):
    categorias = [
        dict(linha, produtos=[])
        for linha in db.execute(
            "SELECT id, nome, tipo FROM categorias WHERE ativo = 1 AND excluido = 0 ORDER BY ordem, id"
        )
    ]
    por_id = {c["id"]: c for c in categorias}
    for produto in db.execute(
        """SELECT id, categoria_id, nome, descricao, preco, imagem FROM produtos
           WHERE ativo = 1 AND excluido = 0 ORDER BY lower(nome)"""
    ):
        if produto["categoria_id"] in por_id:
            por_id[produto["categoria_id"]]["produtos"].append(dict(produto))
    bordas = [
        dict(linha)
        for linha in db.execute("SELECT id, nome, preco FROM bordas WHERE ativo = 1 AND excluido = 0 ORDER BY preco, nome")
    ]
    return dict(categorias=[c for c in categorias if c["produtos"]], bordas=bordas)


@api.get("/cardapio")
def cardapio():
    return jsonify(cardapio_publico(get_db()))


@api.get("/versao")
def versao():
    """Contadores de mudança que as telas consultam a cada poucos segundos.

    A resposta é igual para todo mundo e não usa sessão; assim a CDN pode guardá-la por 2 segundos e
    várias telas abertas custam uma única consulta ao banco.
    """
    resposta = jsonify(versoes=versoes(get_db()), agora=agora())
    resposta.headers["Cache-Control"] = "public, max-age=0, s-maxage=2"
    return resposta


@api.get("/mesa/<int:numero>")
def mesa_cliente(numero):
    db = get_db()
    return jsonify(servicos.situacao_mesa(db, servicos.mesa_autorizada(db, numero, _codigo())))


@api.post("/mesa/<int:numero>/pedidos")
def pedido_cliente(numero):
    db = get_db()
    dados = request.get_json(silent=True) or {}
    mesa = servicos.mesa_autorizada(db, numero, _codigo())
    # Esta rota é aberta; o limite impede que alguém de fora encha a cozinha de pedidos falsos.
    desde = (agora_dt() - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    recentes = db.execute(
        "SELECT COUNT(*) FROM pedidos WHERE mesa_id = ? AND origem = 'cliente' AND criado_em >= ?", (mesa["id"], desde)
    ).fetchone()[0]
    if recentes >= MAX_PEDIDOS_POR_MESA:
        raise servicos.Erro("Muitos pedidos desta mesa em pouco tempo. Chame um garçom para continuar.", 429)
    pedido_id = servicos.criar_pedido(db, mesa, dados.get("itens"), "cliente")
    publicar("pedidos")
    return jsonify(pedido_id=pedido_id), 201


@api.post("/mesa/<int:numero>/chamar")
def chamar(numero):
    db = get_db()
    tipo = (request.get_json(silent=True) or {}).get("tipo")
    if tipo not in ("garcom", "conta"):
        raise servicos.Erro("Chamado inválido.")
    mesa = servicos.mesa_autorizada(db, numero, _codigo())
    if mesa["chamado"] != tipo:  # repetir o mesmo chamado não gera novo aviso
        with db:
            db.execute("UPDATE mesas SET chamado = ?, chamado_em = ? WHERE id = ?", (tipo, agora(), mesa["id"]))
        publicar("mesas")
    return jsonify(ok=True)


# ---------- API da equipe ----------

@api.get("/mesas")
@exige("garcom", "admin")
def mesas():
    return jsonify(servicos.listar_mesas(get_db()))


@api.get("/mesas/<int:mesa_id>")
@exige("garcom", "admin")
def mesa_detalhe(mesa_id):
    db = get_db()
    return jsonify(servicos.situacao_mesa(db, servicos.mesa_por_id(db, mesa_id)))


@api.post("/mesas/<int:mesa_id>/pedidos")
@exige("garcom", "admin")
def pedido_garcom(mesa_id):
    db = get_db()
    dados = request.get_json(silent=True) or {}
    mesa = servicos.mesa_por_id(db, mesa_id)
    pedido_id = servicos.criar_pedido(db, mesa, dados.get("itens"), "garcom", g.usuario["id"])
    publicar("pedidos")
    return jsonify(pedido_id=pedido_id), 201


@api.post("/mesas/<int:mesa_id>/atender")
@exige("garcom", "admin")
def atender(mesa_id):
    db = get_db()
    mesa = servicos.mesa_por_id(db, mesa_id)
    with db:
        db.execute("UPDATE mesas SET chamado = NULL, chamado_em = NULL WHERE id = ?", (mesa["id"],))
    publicar("mesas")
    return jsonify(ok=True)


@api.get("/cozinha/pedidos")
@exige("cozinha", "admin")
def fila_cozinha():
    return jsonify(servicos.pedidos_da_cozinha(get_db()))


@api.post("/pedidos/<int:pedido_id>/status")
@exige("cozinha", "garcom", "admin")
def status_pedido(pedido_id):
    novo = (request.get_json(silent=True) or {}).get("status")
    servicos.mudar_status_pedido(get_db(), pedido_id, novo, g.usuario["perfil"])
    publicar("pedidos")
    return jsonify(ok=True)
