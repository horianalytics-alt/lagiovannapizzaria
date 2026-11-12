import time
from functools import wraps

from flask import Blueprint, g, jsonify, redirect, request, session, url_for
from werkzeug.security import check_password_hash

from .db import get_db

bp = Blueprint("auth", __name__)

INICIO_POR_PERFIL = {"admin": "/admin", "garcom": "/garcom", "cozinha": "/cozinha"}
MAX_TENTATIVAS = 8
JANELA_SEGUNDOS = 300
_tentativas = {}


def carregar_usuario():
    g.usuario = None
    uid = session.get("uid")
    if uid is not None:
        g.usuario = get_db().execute(
            "SELECT id, nome, usuario, perfil FROM usuarios WHERE id = ? AND ativo = 1", (uid,)
        ).fetchone()
        if g.usuario is None:
            session.clear()


def exige(*perfis):
    """Protege rotas da API: 401 sem login, 403 se o perfil não tem acesso."""

    def decorador(funcao):
        @wraps(funcao)
        def interna(*args, **kwargs):
            if g.usuario is None:
                return jsonify(erro="Sua sessão terminou. Entre de novo."), 401
            if g.usuario["perfil"] not in perfis:
                return jsonify(erro="Seu perfil não tem acesso a esta área."), 403
            return funcao(*args, **kwargs)

        return interna

    return decorador


def pagina_exige(*perfis):
    """Protege páginas: sem login vai para /entrar; perfil errado vai para a própria área."""

    def decorador(funcao):
        @wraps(funcao)
        def interna(*args, **kwargs):
            if g.usuario is None:
                return redirect(url_for("paginas.entrar", proximo=request.path))
            if g.usuario["perfil"] not in perfis:
                return redirect(INICIO_POR_PERFIL[g.usuario["perfil"]])
            return funcao(*args, **kwargs)

        return interna

    return decorador


def _bloqueado(chave):
    agora = time.time()
    recentes = [t for t in _tentativas.get(chave, []) if agora - t < JANELA_SEGUNDOS]
    _tentativas[chave] = recentes
    return len(recentes) >= MAX_TENTATIVAS


@bp.post("/api/login")
def login():
    dados = request.get_json(silent=True) or {}
    usuario = str(dados.get("usuario", "")).strip().lower()
    senha = str(dados.get("senha", ""))
    chave = (request.remote_addr, usuario)
    if _bloqueado(chave):
        return jsonify(erro="Muitas tentativas. Espere alguns minutos e tente de novo."), 429
    linha = get_db().execute(
        "SELECT id, nome, perfil, senha_hash FROM usuarios WHERE usuario = ? AND ativo = 1", (usuario,)
    ).fetchone()
    if not linha or not check_password_hash(linha["senha_hash"], senha):
        _tentativas.setdefault(chave, []).append(time.time())
        return jsonify(erro="Usuário ou senha incorretos."), 401
    _tentativas.pop(chave, None)
    session.clear()
    session["uid"] = linha["id"]
    session.permanent = True
    return jsonify(nome=linha["nome"], perfil=linha["perfil"], inicio=INICIO_POR_PERFIL[linha["perfil"]])


@bp.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@bp.get("/api/eu")
def eu():
    if g.usuario is None:
        return jsonify(erro="Sua sessão terminou. Entre de novo."), 401
    return jsonify(dict(g.usuario))
