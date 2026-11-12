import os
import time
from datetime import timedelta
from pathlib import Path

from flask import Flask, jsonify, request
from werkzeug.middleware.proxy_fix import ProxyFix

from . import admin, auth, rotas, seed
from .db import abrir, chave_secreta, criar_tabelas, fechar_db
from .servicos import Erro

RAIZ = Path(__file__).resolve().parent.parent


def banco_configurado(pasta_dados=None, url_banco=None):
    """Postgres quando há DATABASE_URL (nuvem); senão, um arquivo SQLite na pasta de dados."""
    url = url_banco or os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
    if url:
        return ("postgres", url)
    pasta = Path(pasta_dados or os.environ.get("LAGIOVANNA_DADOS") or RAIZ / "dados")
    pasta.mkdir(parents=True, exist_ok=True)
    return ("sqlite", str(pasta / "lagiovanna.db"))


def create_app(pasta_dados=None, url_banco=None):
    banco = banco_configurado(pasta_dados, url_banco)
    na_nuvem = bool(os.environ.get("VERCEL"))

    # Os arquivos estáticos ficam em public/static: na Vercel a CDN os entrega direto, sem passar pelo Python.
    app = Flask(
        __name__, template_folder=str(RAIZ / "templates"), static_folder=str(RAIZ / "public" / "static"),
        static_url_path="/static",
    )

    db = abrir(*banco)
    criar_tabelas(db)
    seed.popular_se_vazio(db)
    segredo = chave_secreta(db)
    db.close()

    app.config.update(
        BANCO=banco,
        SECRET_KEY=segredo,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=na_nuvem,
        SESSION_REFRESH_EACH_REQUEST=False,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=16),
        MAX_CONTENT_LENGTH=4 * 1024 * 1024,
        VERSAO=(os.environ.get("VERCEL_GIT_COMMIT_SHA") or str(int(time.time())))[:10],
    )
    app.json.ensure_ascii = False
    if na_nuvem:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    app.teardown_appcontext(fechar_db)
    app.before_request(auth.carregar_usuario)
    app.register_blueprint(auth.bp)
    app.register_blueprint(rotas.paginas)
    app.register_blueprint(rotas.api)
    app.register_blueprint(admin.bp)

    @app.context_processor
    def _contexto():
        return dict(versao=app.config["VERSAO"])

    @app.errorhandler(Erro)
    def _erro_de_regra(erro):
        return jsonify(erro=erro.mensagem), erro.codigo

    @app.errorhandler(413)
    def _arquivo_grande(_erro):
        return jsonify(erro="A imagem é grande demais. Use um arquivo de até 4 MB."), 413

    @app.errorhandler(404)
    def _nao_encontrado(erro):
        if request.path.startswith("/api/"):
            return jsonify(erro="Não encontrado."), 404
        return erro

    @app.after_request
    def _cabecalhos(resposta):
        resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
        resposta.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        if request.path.startswith("/api/") and "Cache-Control" not in resposta.headers:
            resposta.headers["Cache-Control"] = "no-store"
        return resposta

    return app
