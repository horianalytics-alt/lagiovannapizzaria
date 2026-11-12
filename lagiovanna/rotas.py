"""Páginas e API usadas por cliente, garçom e cozinha."""
from flask import (
    Blueprint, Response, current_app, g, jsonify, redirect, render_template, request, send_from_directory, session,
)

from . import servicos
from .auth import INICIO_POR_PERFIL, exige, pagina_exige
from .db import agora, get_db
from .eventos import canal, fluxo_sse

paginas = Blueprint("paginas", __name__)
api = Blueprint("api", __name__, url_prefix="/api")


# ---------- Páginas ----------

@paginas.get("/")
def inicio():
    return render_template("inicio.html")


@paginas.get("/entrar")
def entrar():
    if g.usuario is not None:
        return redirect(INICIO_POR_PERFIL[g.usuario["perfil"]])
    return render_template("app.html", modulo="entrar", titulo="Entrar", tema="claro")


@paginas.get("/sair")
def sair():
    session.clear()
    return redirect("/entrar")


@paginas.get("/mesa/<int:numero>")
def mesa(numero):
    existe = get_db().execute("SELECT 1 FROM mesas WHERE numero = ? AND ativo = 1", (numero,)).fetchone()
    if not existe:
        return render_template("inicio.html", aviso=f"A mesa {numero:02d} não existe. Confira o número na sua mesa."), 404
    return render_template("app.html", modulo="cliente", titulo=f"Mesa {numero:02d}", tema="claro", dados={"mesa": numero})


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
    return send_from_directory(current_app.config["PASTA_UPLOADS"], nome, max_age=86400)


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
           WHERE ativo = 1 AND excluido = 0 ORDER BY nome COLLATE NOCASE"""
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


@api.get("/eventos")
def eventos():
    resposta = Response(fluxo_sse(), mimetype="text/event-stream")
    resposta.headers["Cache-Control"] = "no-cache"
    resposta.headers["X-Accel-Buffering"] = "no"
    return resposta


@api.get("/mesa/<int:numero>")
def mesa_cliente(numero):
    db = get_db()
    return jsonify(servicos.situacao_mesa(db, servicos.mesa_por_numero(db, numero)))


@api.post("/mesa/<int:numero>/pedidos")
def pedido_cliente(numero):
    db = get_db()
    dados = request.get_json(silent=True) or {}
    mesa = servicos.mesa_por_numero(db, numero)
    pedido_id = servicos.criar_pedido(db, mesa, dados.get("itens"), "cliente")
    canal.publicar("pedidos")
    return jsonify(pedido_id=pedido_id), 201


@api.post("/mesa/<int:numero>/chamar")
def chamar(numero):
    db = get_db()
    tipo = (request.get_json(silent=True) or {}).get("tipo")
    if tipo not in ("garcom", "conta"):
        raise servicos.Erro("Chamado inválido.")
    mesa = servicos.mesa_por_numero(db, numero)
    with db:
        db.execute("UPDATE mesas SET chamado = ?, chamado_em = ? WHERE id = ?", (tipo, agora(), mesa["id"]))
    canal.publicar("mesas")
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
    canal.publicar("pedidos")
    return jsonify(pedido_id=pedido_id), 201


@api.post("/mesas/<int:mesa_id>/atender")
@exige("garcom", "admin")
def atender(mesa_id):
    db = get_db()
    mesa = servicos.mesa_por_id(db, mesa_id)
    with db:
        db.execute("UPDATE mesas SET chamado = NULL, chamado_em = NULL WHERE id = ?", (mesa["id"],))
    canal.publicar("mesas")
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
    canal.publicar("pedidos")
    return jsonify(ok=True)
