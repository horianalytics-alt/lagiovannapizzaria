"""Login, sessão e permissões da equipe."""
import hashlib
import re
from datetime import timedelta
from functools import wraps
from urllib.parse import urlsplit

from flask import Blueprint, current_app, g, jsonify, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .db import agora, agora_dt, get_db

bp = Blueprint("auth", __name__)

INICIO_POR_PERFIL = {"admin": "/admin", "garcom": "/garcom", "cozinha": "/cozinha"}
SENHA_MINIMA = 8
JANELA_MINUTOS = 15
MAX_POR_USUARIO = 8
MAX_POR_ENDERECO = 30
# Rotas que continuam liberadas para quem ainda precisa definir uma senha nova.
LIBERADAS_SEM_SENHA_NOVA = {"auth.minha_senha", "auth.logout", "auth.eu"}
# Conferir a senha contra um hash falso quando o usuário não existe deixa o tempo de resposta igual.
_HASH_FALSO = generate_password_hash("senha-que-ninguem-usa")


def _marca_da_senha(senha_hash):
    """Vai na sessão; se a senha mudar, as sessões antigas deixam de valer."""
    return hashlib.sha256(senha_hash.encode()).hexdigest()[:16]


def carregar_usuario():
    g.usuario = None
    # /api/versao não toca na sessão para poder ser guardada pela CDN.
    if request.endpoint in ("api.versao", "static", "paginas.upload"):
        return
    uid = session.get("uid")
    if uid is None:
        return
    linha = get_db().execute(
        "SELECT id, nome, usuario, perfil, senha_hash, trocar_senha FROM usuarios WHERE id = ? AND ativo = 1", (uid,)
    ).fetchone()
    if linha is None or session.get("sv") != _marca_da_senha(linha["senha_hash"]):
        session.clear()
        return
    g.usuario = {chave: linha[chave] for chave in ("id", "nome", "usuario", "perfil", "trocar_senha")}


def conferir_origem():
    """Recusa alterações vindas de outro site (reforço contra CSRF, além do cookie SameSite)."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return None
    origem = request.headers.get("Origin")
    if origem and urlsplit(origem).netloc != request.host:
        return jsonify(erro="Requisição recusada."), 403
    return None


def exige(*perfis):
    """Protege rotas da API: 401 sem login, 403 se o perfil não tem acesso ou falta trocar a senha."""

    def decorador(funcao):
        @wraps(funcao)
        def interna(*args, **kwargs):
            if g.usuario is None:
                return jsonify(erro="Sua sessão terminou. Entre de novo."), 401
            if g.usuario["trocar_senha"] and request.endpoint not in LIBERADAS_SEM_SENHA_NOVA:
                return jsonify(erro="Defina uma senha nova para continuar.", trocar_senha=True), 403
            if perfis and g.usuario["perfil"] not in perfis:
                return jsonify(erro="Seu perfil não tem acesso a esta área."), 403
            return funcao(*args, **kwargs)

        return interna

    return decorador


def pagina_exige(*perfis):
    """Protege páginas: sem login vai para /entrar; senha provisória vai para a troca; perfil errado, para a própria área."""

    def decorador(funcao):
        @wraps(funcao)
        def interna(*args, **kwargs):
            if g.usuario is None:
                return redirect(url_for("paginas.entrar", proximo=request.path))
            if g.usuario["trocar_senha"]:
                return redirect("/trocar-senha")
            if g.usuario["perfil"] not in perfis:
                return redirect(INICIO_POR_PERFIL[g.usuario["perfil"]])
            return funcao(*args, **kwargs)

        return interna

    return decorador


def validar_senha_nova(senha):
    if not isinstance(senha, str) or len(senha) < SENHA_MINIMA:
        return f"A senha precisa ter pelo menos {SENHA_MINIMA} caracteres."
    if len(senha) > 200:
        return "A senha é longa demais."
    if senha.lower() in {"12345678", "123456789", "senha123", "password", "giovanna123", "garcom123", "cozinha123"}:
        return "Essa senha é fácil de adivinhar. Escolha outra."
    return None


# ---------- Limite de tentativas (no banco, para valer em todas as instâncias do servidor) ----------

def _chaves_de_tentativa(usuario):
    # O endereço IP é guardado embaralhado e só por 24 horas.
    endereco = hashlib.sha256(f"{current_app.secret_key}:{request.remote_addr}".encode()).hexdigest()[:20]
    return f"u:{usuario[:40]}", f"ip:{endereco}"


def _bloqueado(db, chave_usuario, chave_endereco):
    desde = (agora_dt() - timedelta(minutes=JANELA_MINUTOS)).strftime("%Y-%m-%d %H:%M:%S")
    contagem = {
        linha["chave"]: linha["total"]
        for linha in db.execute(
            "SELECT chave, COUNT(*) AS total FROM tentativas_login WHERE chave IN (?, ?) AND momento >= ? GROUP BY chave",
            (chave_usuario, chave_endereco, desde),
        )
    }
    return contagem.get(chave_usuario, 0) >= MAX_POR_USUARIO or contagem.get(chave_endereco, 0) >= MAX_POR_ENDERECO


def _registrar_falha(db, chave_usuario, chave_endereco):
    momento = agora()
    ontem = (agora_dt() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    with db:
        db.execute("DELETE FROM tentativas_login WHERE momento < ?", (ontem,))
        db.executemany(
            "INSERT INTO tentativas_login (chave, momento) VALUES (?, ?)",
            [(chave_usuario, momento), (chave_endereco, momento)],
        )


@bp.post("/api/login")
def login():
    db = get_db()
    dados = request.get_json(silent=True) or {}
    usuario = str(dados.get("usuario", "")).strip().lower()
    senha = str(dados.get("senha", ""))
    chaves = _chaves_de_tentativa(usuario)
    if _bloqueado(db, *chaves):
        return jsonify(erro=f"Muitas tentativas. Espere {JANELA_MINUTOS} minutos e tente de novo."), 429
    linha = db.execute(
        "SELECT id, nome, perfil, senha_hash, trocar_senha FROM usuarios WHERE usuario = ? AND ativo = 1", (usuario,)
    ).fetchone()
    confere = check_password_hash(linha["senha_hash"] if linha else _HASH_FALSO, senha[:200])
    if not linha or not confere:
        _registrar_falha(db, *chaves)
        return jsonify(erro="Usuário ou senha incorretos."), 401
    with db:
        db.execute("DELETE FROM tentativas_login WHERE chave = ?", (chaves[0],))
    session.clear()
    session["uid"] = linha["id"]
    session["sv"] = _marca_da_senha(linha["senha_hash"])
    session.permanent = True
    return jsonify(
        nome=linha["nome"], perfil=linha["perfil"], inicio=INICIO_POR_PERFIL[linha["perfil"]],
        trocar_senha=bool(linha["trocar_senha"]),
    )


@bp.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@bp.get("/api/eu")
@exige()
def eu():
    return jsonify(g.usuario)


@bp.post("/api/minha-senha")
@exige()
def minha_senha():
    db = get_db()
    dados = request.get_json(silent=True) or {}
    atual, nova = str(dados.get("atual", "")), dados.get("nova")
    linha = db.execute("SELECT senha_hash FROM usuarios WHERE id = ?", (g.usuario["id"],)).fetchone()
    if not check_password_hash(linha["senha_hash"], atual[:200]):
        return jsonify(erro="A senha atual não confere."), 400
    problema = validar_senha_nova(nova)
    if problema:
        return jsonify(erro=problema), 400
    if nova == atual:
        return jsonify(erro="A senha nova precisa ser diferente da atual."), 400
    novo_hash = generate_password_hash(nova)
    with db:
        db.execute("UPDATE usuarios SET senha_hash = ?, trocar_senha = 0 WHERE id = ?", (novo_hash, g.usuario["id"]))
    session["sv"] = _marca_da_senha(novo_hash)
    return jsonify(ok=True, inicio=INICIO_POR_PERFIL[g.usuario["perfil"]])


def destino_seguro(caminho):
    """Só aceita caminhos internos simples, para o login não servir de trampolim para outro site."""
    return caminho if caminho and re.fullmatch(r"/[a-z0-9/_-]{0,80}", caminho) else None
