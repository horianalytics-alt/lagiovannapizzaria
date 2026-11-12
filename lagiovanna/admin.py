"""API da gerência: cardápio, caixa, mesas e QR Codes, equipe e indicadores."""
import io
import re
import socket
import uuid
from pathlib import Path

import segno
from flask import Blueprint, Response, g, jsonify, render_template, request
from werkzeug.security import generate_password_hash

from . import servicos
from .auth import exige, pagina_exige
from .db import get_db
from .eventos import publicar
from .servicos import Erro

bp = Blueprint("admin", __name__)

TIPOS_CATEGORIA = ("pizza", "bebida", "outro")
PERFIS = ("admin", "garcom", "cozinha")
# extensão -> (assinatura no início do arquivo, tipo)
IMAGENS = {
    ".png": (b"\x89PNG", "image/png"),
    ".jpg": (b"\xff\xd8\xff", "image/jpeg"),
    ".jpeg": (b"\xff\xd8\xff", "image/jpeg"),
    ".webp": (b"RIFF", "image/webp"),
}


def _corpo():
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict):
        raise Erro("Dados inválidos.")
    return dados


def _nome(dados, campo="nome", limite=60):
    valor = dados.get(campo)
    if not isinstance(valor, str) or not valor.strip():
        raise Erro("Informe o nome.")
    return " ".join(valor.split())[:limite]


def _preco(dados):
    valor = dados.get("preco")
    if isinstance(valor, bool) or not isinstance(valor, int) or not 0 <= valor <= 1_000_000:
        raise Erro("Informe um preço válido.")
    return valor


def _existe(db, tabela, registro_id):
    linha = db.execute(f"SELECT * FROM {tabela} WHERE id = ? AND excluido = 0", (registro_id,)).fetchone()
    if not linha:
        raise Erro("Registro não encontrado.", 404)
    return linha


# ---------- Cardápio ----------

@bp.get("/api/admin/cardapio")
@exige("admin")
def cardapio():
    db = get_db()
    return jsonify(
        categorias=[
            dict(l)
            for l in db.execute(
                "SELECT id, nome, tipo, ordem, ativo FROM categorias WHERE excluido = 0 ORDER BY ordem, id"
            )
        ],
        produtos=[
            dict(l)
            for l in db.execute(
                """SELECT id, categoria_id, nome, descricao, preco, imagem, ativo FROM produtos
                   WHERE excluido = 0 ORDER BY lower(nome)"""
            )
        ],
        bordas=[
            dict(l)
            for l in db.execute("SELECT id, nome, preco, ativo FROM bordas WHERE excluido = 0 ORDER BY preco, nome")
        ],
    )


def _dados_categoria(dados):
    tipo = dados.get("tipo", "outro")
    if tipo not in TIPOS_CATEGORIA:
        raise Erro("Tipo de categoria inválido.")
    return _nome(dados), tipo, 1 if dados.get("ativo", True) else 0


@bp.post("/api/admin/categorias")
@exige("admin")
def criar_categoria():
    db = get_db()
    nome, tipo, ativo = _dados_categoria(_corpo())
    with db:
        ordem = db.execute("SELECT COALESCE(MAX(ordem), 0) + 1 FROM categorias").fetchone()[0]
        novo = db.inserir(
            "INSERT INTO categorias (nome, tipo, ordem, ativo) VALUES (?, ?, ?, ?)", (nome, tipo, ordem, ativo)
        )
    publicar("cardapio")
    return jsonify(id=novo), 201


@bp.put("/api/admin/categorias/<int:categoria_id>")
@exige("admin")
def editar_categoria(categoria_id):
    db = get_db()
    _existe(db, "categorias", categoria_id)
    nome, tipo, ativo = _dados_categoria(_corpo())
    with db:
        db.execute("UPDATE categorias SET nome = ?, tipo = ?, ativo = ? WHERE id = ?", (nome, tipo, ativo, categoria_id))
    publicar("cardapio")
    return jsonify(ok=True)


@bp.delete("/api/admin/categorias/<int:categoria_id>")
@exige("admin")
def excluir_categoria(categoria_id):
    db = get_db()
    _existe(db, "categorias", categoria_id)
    em_uso = db.execute(
        "SELECT COUNT(*) FROM produtos WHERE categoria_id = ? AND excluido = 0", (categoria_id,)
    ).fetchone()[0]
    if em_uso:
        raise Erro(f"Esta categoria ainda tem {em_uso} produto(s). Mova ou exclua os produtos antes.", 409)
    with db:
        db.execute("UPDATE categorias SET excluido = 1 WHERE id = ?", (categoria_id,))
    publicar("cardapio")
    return jsonify(ok=True)


@bp.post("/api/admin/categorias/ordem")
@exige("admin")
def ordenar_categorias():
    db = get_db()
    ids = _corpo().get("ids")
    if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids):
        raise Erro("Ordem inválida.")
    with db:
        for posicao, categoria_id in enumerate(ids, start=1):
            db.execute("UPDATE categorias SET ordem = ? WHERE id = ?", (posicao, categoria_id))
    publicar("cardapio")
    return jsonify(ok=True)


def _dados_produto(db, dados):
    categoria_id = dados.get("categoria_id")
    if not isinstance(categoria_id, int):
        raise Erro("Escolha a categoria.")
    _existe(db, "categorias", categoria_id)
    descricao = dados.get("descricao") or ""
    if not isinstance(descricao, str):
        raise Erro("Descrição inválida.")
    imagem = dados.get("imagem") or None
    if imagem is not None and not (
        isinstance(imagem, str) and re.fullmatch(r"/(uploads|static/img/cardapio)/[\w.-]+", imagem)
    ):
        raise Erro("Imagem inválida.")
    return (
        categoria_id,
        _nome(dados),
        " ".join(descricao.split())[:240],
        _preco(dados),
        imagem,
        1 if dados.get("ativo", True) else 0,
    )


@bp.post("/api/admin/produtos")
@exige("admin")
def criar_produto():
    db = get_db()
    valores = _dados_produto(db, _corpo())
    with db:
        novo = db.inserir(
            "INSERT INTO produtos (categoria_id, nome, descricao, preco, imagem, ativo) VALUES (?, ?, ?, ?, ?, ?)",
            valores,
        )
    publicar("cardapio")
    return jsonify(id=novo), 201


@bp.put("/api/admin/produtos/<int:produto_id>")
@exige("admin")
def editar_produto(produto_id):
    db = get_db()
    _existe(db, "produtos", produto_id)
    valores = _dados_produto(db, _corpo())
    with db:
        db.execute(
            """UPDATE produtos SET categoria_id = ?, nome = ?, descricao = ?, preco = ?, imagem = ?, ativo = ?
               WHERE id = ?""",
            (*valores, produto_id),
        )
    publicar("cardapio")
    return jsonify(ok=True)


@bp.post("/api/admin/<any(produtos, bordas, categorias):tabela>/<int:registro_id>/ativo")
@exige("admin")
def pausar(tabela, registro_id):
    db = get_db()
    _existe(db, tabela, registro_id)
    ativo = 1 if _corpo().get("ativo") else 0
    with db:
        db.execute(f"UPDATE {tabela} SET ativo = ? WHERE id = ?", (ativo, registro_id))
    publicar("cardapio")
    return jsonify(ok=True)


@bp.delete("/api/admin/<any(produtos, bordas):tabela>/<int:registro_id>")
@exige("admin")
def excluir(tabela, registro_id):
    db = get_db()
    _existe(db, tabela, registro_id)
    with db:
        db.execute(f"UPDATE {tabela} SET excluido = 1 WHERE id = ?", (registro_id,))
    publicar("cardapio")
    return jsonify(ok=True)


@bp.post("/api/admin/bordas")
@exige("admin")
def criar_borda():
    db = get_db()
    dados = _corpo()
    with db:
        novo = db.inserir("INSERT INTO bordas (nome, preco) VALUES (?, ?)", (_nome(dados), _preco(dados)))
    publicar("cardapio")
    return jsonify(id=novo), 201


@bp.put("/api/admin/bordas/<int:borda_id>")
@exige("admin")
def editar_borda(borda_id):
    db = get_db()
    _existe(db, "bordas", borda_id)
    dados = _corpo()
    with db:
        db.execute("UPDATE bordas SET nome = ?, preco = ? WHERE id = ?", (_nome(dados), _preco(dados), borda_id))
    publicar("cardapio")
    return jsonify(ok=True)


@bp.post("/api/admin/upload")
@exige("admin")
def enviar_imagem():
    arquivo = request.files.get("imagem")
    if not arquivo or not arquivo.filename:
        raise Erro("Escolha uma imagem.")
    extensao = Path(arquivo.filename).suffix.lower()
    conteudo = arquivo.stream.read()
    if extensao not in IMAGENS or not conteudo.startswith(IMAGENS[extensao][0]):
        raise Erro("Use uma imagem JPG, PNG ou WebP.")
    # A foto fica no banco: hospedagens como a Vercel não têm disco que guarde arquivos.
    nome = f"{uuid.uuid4().hex}{extensao}"
    db = get_db()
    with db:
        db.execute("INSERT INTO imagens (nome, tipo, dados) VALUES (?, ?, ?)", (nome, IMAGENS[extensao][1], conteudo))
    return jsonify(url=f"/uploads/{nome}"), 201


# ---------- Caixa ----------

@bp.post("/api/admin/mesas/<int:mesa_id>/fechar")
@exige("admin")
def fechar(mesa_id):
    db = get_db()
    dados = _corpo()
    mesa = servicos.mesa_por_id(db, mesa_id)
    resumo = servicos.fechar_conta(
        db,
        mesa,
        dados.get("desconto", 0),
        dados.get("taxa_servico_pct", 0),
        dados.get("pagamentos", []),
        g.usuario["id"],
    )
    publicar("pedidos", "mesas", "caixa")
    return jsonify(resumo)


@bp.delete("/api/admin/itens/<int:item_id>")
@exige("admin")
def estornar(item_id):
    servicos.estornar_item(get_db(), item_id)
    publicar("pedidos")
    return jsonify(ok=True)


@bp.get("/api/admin/contas")
@exige("admin")
def contas():
    return jsonify(servicos.contas_fechadas(get_db(), request.args.get("dia")))


@bp.post("/api/admin/zerar-vendas")
@exige("admin")
def zerar_vendas():
    if _corpo().get("confirmacao") != "ZERAR":
        raise Erro("Confirmação inválida.")
    servicos.zerar_movimento(get_db())
    publicar("pedidos", "mesas", "caixa")
    return jsonify(ok=True)


@bp.get("/api/admin/indicadores")
@exige("admin")
def indicadores():
    return jsonify(servicos.indicadores(get_db(), request.args.get("dia")))


# ---------- Mesas e QR Codes ----------

def _ip_da_rede():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return None


def endereco_base(db):
    linha = db.execute("SELECT valor FROM config WHERE chave = 'url_base'").fetchone()
    return (linha["valor"] if linha else request.host_url).rstrip("/")


def _link_mesa(base, numero):
    return f"{base}/mesa/{numero:02d}"


@bp.get("/api/admin/mesas")
@exige("admin")
def mesas():
    db = get_db()
    base = endereco_base(db)
    salvo = db.execute("SELECT valor FROM config WHERE chave = 'url_base'").fetchone()
    ip = _ip_da_rede()
    porta = request.host.rsplit(":", 1)[1] if ":" in request.host else None
    return jsonify(
        url_base=base,
        url_base_definida=bool(salvo),
        sugestao_rede=f"http://{ip}{':' + porta if porta else ''}" if ip and not ip.startswith("127.") else None,
        mesas=[
            dict(id=m["id"], numero=m["numero"], link=_link_mesa(base, m["numero"]))
            for m in db.execute("SELECT id, numero FROM mesas WHERE ativo = 1 ORDER BY numero")
        ],
    )


@bp.put("/api/admin/config/url_base")
@exige("admin")
def salvar_endereco():
    db = get_db()
    valor = str(_corpo().get("url_base") or "").strip().rstrip("/")
    with db:
        if not valor:
            db.execute("DELETE FROM config WHERE chave = 'url_base'")
        elif re.fullmatch(r"https?://[\w.-]+(:\d+)?(/[\w./-]*)?", valor):
            db.execute(
                "INSERT INTO config (chave, valor) VALUES ('url_base', ?) "
                "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
                (valor,),
            )
        else:
            raise Erro("Endereço inválido. Exemplo: http://192.168.0.10:5000")
    return jsonify(ok=True)


@bp.post("/api/admin/mesas")
@exige("admin")
def criar_mesa():
    db = get_db()
    numero = _corpo().get("numero")
    if isinstance(numero, bool) or not isinstance(numero, int) or not 1 <= numero <= 999:
        raise Erro("Informe um número de mesa entre 1 e 999.")
    existente = db.execute("SELECT id, ativo FROM mesas WHERE numero = ?", (numero,)).fetchone()
    if existente and existente["ativo"]:
        raise Erro(f"A mesa {numero:02d} já existe.", 409)
    with db:
        if existente:
            db.execute("UPDATE mesas SET ativo = 1, chamado = NULL, chamado_em = NULL WHERE id = ?", (existente["id"],))
        else:
            db.execute("INSERT INTO mesas (numero) VALUES (?)", (numero,))
    publicar("mesas")
    return jsonify(ok=True), 201


@bp.delete("/api/admin/mesas/<int:mesa_id>")
@exige("admin")
def excluir_mesa(mesa_id):
    db = get_db()
    mesa = servicos.mesa_por_id(db, mesa_id)
    if servicos.comanda_aberta(db, mesa["id"]):
        raise Erro("Esta mesa tem conta aberta. Feche a conta antes de excluir.", 409)
    with db:
        db.execute("UPDATE mesas SET ativo = 0, chamado = NULL, chamado_em = NULL WHERE id = ?", (mesa_id,))
    publicar("mesas")
    return jsonify(ok=True)


def _qr(link):
    return segno.make(link, error="m")


@bp.get("/api/admin/mesas/<int:mesa_id>/qr.svg")
@exige("admin")
def qr_svg(mesa_id):
    db = get_db()
    mesa = servicos.mesa_por_id(db, mesa_id)
    saida = io.BytesIO()
    _qr(_link_mesa(endereco_base(db), mesa["numero"])).save(saida, kind="svg", scale=10, border=2, dark="#2b1a17")
    resposta = Response(saida.getvalue(), mimetype="image/svg+xml")
    resposta.headers["Cache-Control"] = "no-store"
    if request.args.get("baixar"):
        resposta.headers["Content-Disposition"] = f'attachment; filename="mesa-{mesa["numero"]:02d}.svg"'
    return resposta


@bp.get("/admin/qrcodes")
@pagina_exige("admin")
def imprimir_qrcodes():
    db = get_db()
    base = endereco_base(db)
    mesas = [
        dict(
            numero=m["numero"],
            link=_link_mesa(base, m["numero"]),
            svg=_qr(_link_mesa(base, m["numero"])).svg_inline(scale=6, border=1, dark="#2b1a17"),
        )
        for m in db.execute("SELECT numero FROM mesas WHERE ativo = 1 ORDER BY numero")
    ]
    return render_template("qrcodes.html", mesas=mesas)


# ---------- Equipe ----------

@bp.get("/api/admin/usuarios")
@exige("admin")
def usuarios():
    return jsonify(
        [dict(l) for l in get_db().execute("SELECT id, nome, usuario, perfil, ativo FROM usuarios ORDER BY nome")]
    )


def _senha(dados, obrigatoria):
    senha = dados.get("senha")
    if not senha and not obrigatoria:
        return None
    if not isinstance(senha, str) or len(senha) < 6:
        raise Erro("A senha precisa ter pelo menos 6 caracteres.")
    return generate_password_hash(senha)


def _perfil(dados):
    if dados.get("perfil") not in PERFIS:
        raise Erro("Perfil inválido.")
    return dados["perfil"]


@bp.post("/api/admin/usuarios")
@exige("admin")
def criar_usuario():
    db = get_db()
    dados = _corpo()
    usuario = str(dados.get("usuario", "")).strip().lower()
    if not re.fullmatch(r"[a-z0-9._-]{3,30}", usuario):
        raise Erro("O usuário deve ter de 3 a 30 letras minúsculas, números, ponto ou hífen.")
    if db.execute("SELECT 1 FROM usuarios WHERE usuario = ?", (usuario,)).fetchone():
        raise Erro("Já existe alguém com esse usuário.", 409)
    with db:
        db.execute(
            "INSERT INTO usuarios (nome, usuario, senha_hash, perfil) VALUES (?, ?, ?, ?)",
            (_nome(dados), usuario, _senha(dados, True), _perfil(dados)),
        )
    return jsonify(ok=True), 201


@bp.put("/api/admin/usuarios/<int:usuario_id>")
@exige("admin")
def editar_usuario(usuario_id):
    db = get_db()
    dados = _corpo()
    if not db.execute("SELECT 1 FROM usuarios WHERE id = ?", (usuario_id,)).fetchone():
        raise Erro("Pessoa não encontrada.", 404)
    perfil, ativo = _perfil(dados), 1 if dados.get("ativo", True) else 0
    if usuario_id == g.usuario["id"] and (perfil != "admin" or not ativo):
        raise Erro("Você não pode tirar o próprio acesso de gerente.", 409)
    senha_hash = _senha(dados, False)
    with db:
        db.execute("UPDATE usuarios SET nome = ?, perfil = ?, ativo = ? WHERE id = ?", (_nome(dados), perfil, ativo, usuario_id))
        if senha_hash:
            db.execute("UPDATE usuarios SET senha_hash = ? WHERE id = ?", (senha_hash, usuario_id))
    return jsonify(ok=True)
