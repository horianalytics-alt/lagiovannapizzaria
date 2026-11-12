import os
import secrets
import time
from datetime import timedelta
from pathlib import Path

from flask import Flask, jsonify, request

from . import admin, auth, rotas, seed
from .db import conectar, criar_tabelas, fechar_db
from .servicos import Erro

RAIZ = Path(__file__).resolve().parent.parent


def _chave_secreta(pasta):
    arquivo = pasta / "secret.key"
    if not arquivo.exists():
        arquivo.write_text(secrets.token_hex(32))
    return arquivo.read_text().strip()


def create_app(pasta_dados=None):
    pasta = Path(pasta_dados or os.environ.get("LAGIOVANNA_DADOS") or RAIZ / "dados")
    uploads = pasta / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)

    app = Flask(__name__, template_folder=str(RAIZ / "templates"), static_folder=str(RAIZ / "static"))
    app.config.update(
        BANCO=str(pasta / "lagiovanna.db"),
        PASTA_UPLOADS=str(uploads),
        SECRET_KEY=_chave_secreta(pasta),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=16),
        MAX_CONTENT_LENGTH=6 * 1024 * 1024,
        VERSAO=str(int(time.time())),
    )
    app.json.ensure_ascii = False

    con = conectar(app.config["BANCO"])
    criar_tabelas(con)
    seed.popular_se_vazio(con)
    con.close()

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
        return jsonify(erro="A imagem é grande demais. Use um arquivo de até 5 MB."), 413

    @app.errorhandler(404)
    def _nao_encontrado(erro):
        if request.path.startswith("/api/"):
            return jsonify(erro="Não encontrado."), 404
        return erro

    @app.after_request
    def _cabecalhos(resposta):
        resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
        resposta.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        if request.path.startswith("/api/") and resposta.mimetype == "application/json":
            resposta.headers["Cache-Control"] = "no-store"
        return resposta

    return app
