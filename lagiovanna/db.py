"""Acesso ao banco. Funciona igual em SQLite (arquivo local) e Postgres (nuvem, via DATABASE_URL)."""
import os
import secrets
import sqlite3
import threading
import time
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from flask import current_app, g

# Servidores na nuvem rodam em UTC; a pizzaria vive no horário de Brasília.
FUSO = ZoneInfo(os.environ.get("FUSO_HORARIO", "America/Sao_Paulo"))
TOPICOS = ("pedidos", "mesas", "cardapio", "caixa")

SCHEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL,
    usuario TEXT NOT NULL UNIQUE,
    senha_hash TEXT NOT NULL,
    perfil TEXT NOT NULL CHECK (perfil IN ('admin', 'garcom', 'cozinha')),
    ativo INTEGER NOT NULL DEFAULT 1,
    trocar_senha INTEGER NOT NULL DEFAULT 0,
    excluido_em TEXT
);
CREATE TABLE IF NOT EXISTS categorias (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL,
    tipo TEXT NOT NULL DEFAULT 'outro' CHECK (tipo IN ('pizza', 'bebida', 'outro')),
    ordem INTEGER NOT NULL DEFAULT 0,
    ativo INTEGER NOT NULL DEFAULT 1,
    excluido INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS produtos (
    id INTEGER PRIMARY KEY,
    categoria_id INTEGER NOT NULL REFERENCES categorias(id),
    nome TEXT NOT NULL,
    descricao TEXT NOT NULL DEFAULT '',
    preco INTEGER NOT NULL CHECK (preco >= 0),
    imagem TEXT,
    ativo INTEGER NOT NULL DEFAULT 1,
    excluido INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS bordas (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL,
    preco INTEGER NOT NULL CHECK (preco >= 0),
    ativo INTEGER NOT NULL DEFAULT 1,
    excluido INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS mesas (
    id INTEGER PRIMARY KEY,
    numero INTEGER NOT NULL UNIQUE,
    ativo INTEGER NOT NULL DEFAULT 1,
    chamado TEXT CHECK (chamado IN ('garcom', 'conta')),
    chamado_em TEXT
);
CREATE TABLE IF NOT EXISTS comandas (
    id INTEGER PRIMARY KEY,
    mesa_id INTEGER NOT NULL REFERENCES mesas(id),
    status TEXT NOT NULL DEFAULT 'aberta' CHECK (status IN ('aberta', 'fechada')),
    aberta_em TEXT NOT NULL,
    fechada_em TEXT,
    subtotal INTEGER NOT NULL DEFAULT 0,
    desconto INTEGER NOT NULL DEFAULT 0,
    taxa_servico_pct REAL NOT NULL DEFAULT 0,
    taxa_servico INTEGER NOT NULL DEFAULT 0,
    total INTEGER NOT NULL DEFAULT 0,
    fechada_por INTEGER REFERENCES usuarios(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_comanda_aberta ON comandas(mesa_id) WHERE status = 'aberta';
CREATE INDEX IF NOT EXISTS ix_comandas_fechada_em ON comandas(fechada_em);
CREATE TABLE IF NOT EXISTS pagamentos (
    id INTEGER PRIMARY KEY,
    comanda_id INTEGER NOT NULL REFERENCES comandas(id),
    forma TEXT NOT NULL CHECK (forma IN ('dinheiro', 'pix', 'credito', 'debito')),
    valor INTEGER NOT NULL CHECK (valor > 0)
);
CREATE INDEX IF NOT EXISTS ix_pagamentos_comanda ON pagamentos(comanda_id);
CREATE TABLE IF NOT EXISTS pedidos (
    id INTEGER PRIMARY KEY,
    comanda_id INTEGER NOT NULL REFERENCES comandas(id),
    mesa_id INTEGER NOT NULL REFERENCES mesas(id),
    origem TEXT NOT NULL CHECK (origem IN ('cliente', 'garcom')),
    usuario_id INTEGER REFERENCES usuarios(id),
    status TEXT NOT NULL DEFAULT 'pendente'
        CHECK (status IN ('pendente', 'preparo', 'pronto', 'entregue', 'cancelado')),
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_pedidos_comanda ON pedidos(comanda_id);
CREATE INDEX IF NOT EXISTS ix_pedidos_criado_em ON pedidos(criado_em);
CREATE INDEX IF NOT EXISTS ix_pedidos_status ON pedidos(status);
CREATE TABLE IF NOT EXISTS pedido_itens (
    id INTEGER PRIMARY KEY,
    pedido_id INTEGER NOT NULL REFERENCES pedidos(id),
    produto_id INTEGER NOT NULL REFERENCES produtos(id),
    produto2_id INTEGER REFERENCES produtos(id),
    borda_id INTEGER REFERENCES bordas(id),
    descricao TEXT NOT NULL,
    detalhe TEXT,
    observacao TEXT,
    quantidade INTEGER NOT NULL CHECK (quantidade > 0),
    preco_unit INTEGER NOT NULL,
    cancelado INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_itens_pedido ON pedido_itens(pedido_id);
CREATE TABLE IF NOT EXISTS config (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS imagens (
    nome TEXT PRIMARY KEY,
    tipo TEXT NOT NULL,
    dados BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS versoes (
    topico TEXT PRIMARY KEY,
    numero INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS tentativas_login (
    id INTEGER PRIMARY KEY,
    chave TEXT NOT NULL,
    momento TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_tentativas_chave ON tentativas_login(chave, momento)
"""

# Some quando o esquema acima mudar; o servidor só refaz a preparação quando o número gravado é outro.
ESQUEMA = "2"


def agora_dt():
    return datetime.now(FUSO).replace(tzinfo=None, microsecond=0)


def agora():
    return agora_dt().strftime("%Y-%m-%d %H:%M:%S")


def hoje():
    return agora_dt().date()


class Linha:
    """Linha do Postgres com o mesmo jeito de usar do sqlite3.Row: por nome, por posição e dict(linha)."""

    __slots__ = ("_indices", "_valores")

    def __init__(self, indices, valores):
        self._indices = indices
        self._valores = valores

    def __getitem__(self, chave):
        return self._valores[chave if isinstance(chave, int) else self._indices[chave]]

    def keys(self):
        return list(self._indices)

    def __iter__(self):
        return iter(self._valores)

    def __len__(self):
        return len(self._valores)


def _fabrica_de_linhas(cursor):
    indices = {coluna.name: i for i, coluna in enumerate(cursor.description or ())}
    return lambda valores: Linha(indices, valores)


class Banco:
    """Interface única sobre sqlite3 e psycopg. O SQL do sistema usa `?` e só recursos comuns aos dois."""

    def __init__(self, con, postgres):
        self.con = con
        self.postgres = postgres
        self._transacao = None

    def _sql(self, sql):
        return sql.replace("?", "%s") if self.postgres else sql

    def execute(self, sql, parametros=()):
        return self.con.execute(self._sql(sql), parametros)

    def executemany(self, sql, linhas):
        if self.postgres:
            with self.con.cursor() as cursor:
                cursor.executemany(self._sql(sql), linhas)
        else:
            self.con.executemany(sql, linhas)

    def inserir(self, sql, parametros=()):
        """Executa um INSERT e devolve o id gerado."""
        if self.postgres:
            return self.con.execute(self._sql(sql) + " RETURNING id", parametros).fetchone()[0]
        return self.con.execute(sql, parametros).lastrowid

    def __enter__(self):
        if self.postgres:
            self._transacao = self.con.transaction()
            self._transacao.__enter__()
        else:
            self.con.__enter__()
        return self

    def __exit__(self, *erro):
        if self.postgres:
            transacao, self._transacao = self._transacao, None
            return transacao.__exit__(*erro)
        return self.con.__exit__(*erro)

    def close(self):
        if not self.postgres:
            self.con.close()


# ---------- Conexões ----------

_PARAMETROS_ACEITOS = {"sslmode", "channel_binding", "connect_timeout", "options", "application_name", "sslrootcert"}
_da_thread = threading.local()
_OCIOSA_SEGUNDOS = 20


def _limpar_url(url):
    """Tira da URL parâmetros que alguns provedores acrescentam e o driver não conhece."""
    partes = urlsplit(url)
    consulta = [(k, v) for k, v in parse_qsl(partes.query) if k in _PARAMETROS_ACEITOS]
    return urlunsplit(partes._replace(query=urlencode(consulta)))


def _conectar_postgres(url):
    import psycopg

    # prepare_threshold=None: conexões "pooled" (PgBouncer) não aceitam prepared statements.
    return psycopg.connect(
        _limpar_url(url), autocommit=True, prepare_threshold=None, row_factory=_fabrica_de_linhas, connect_timeout=10
    )


def _postgres_da_thread(url):
    """Reaproveita a conexão entre requisições; depois de um tempo parada, confere se ainda está viva."""
    con = getattr(_da_thread, "con", None)
    momento = time.time()
    if con is not None and not con.closed and not con.broken and _da_thread.url == url:
        if momento - _da_thread.uso < _OCIOSA_SEGUNDOS:
            _da_thread.uso = momento
            return con
        try:
            con.execute("SELECT 1")
            _da_thread.uso = momento
            return con
        except Exception:
            pass
    if con is not None:
        try:
            con.close()
        except Exception:
            pass
    con = _conectar_postgres(url)
    _da_thread.con, _da_thread.url, _da_thread.uso = con, url, momento
    return con


def abrir(tipo, alvo):
    if tipo == "postgres":
        return Banco(_postgres_da_thread(alvo), True)
    con = sqlite3.connect(alvo, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    return Banco(con, False)


def get_db():
    if "db" not in g:
        g.db = abrir(*current_app.config["BANCO"])
    return g.db


def fechar_db(_erro=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# ---------- Preparação ----------

def _tem_coluna(db, tabela, coluna):
    if db.postgres:
        return bool(db.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_name = ? AND column_name = ?", (tabela, coluna)
        ).fetchone())
    return any(linha["name"] == coluna for linha in db.execute(f"PRAGMA table_info({tabela})"))


def criar_tabelas(db):
    """Cria o que falta e aplica mudanças de esquema. Com o banco em dia, custa uma única consulta."""
    try:
        gravado = db.execute("SELECT valor FROM config WHERE chave = 'esquema'").fetchone()
    except Exception:  # a tabela config ainda não existe
        gravado = None
    if gravado and gravado[0] == ESQUEMA:
        return
    sql = SCHEMA
    if db.postgres:
        sql = sql.replace("id INTEGER PRIMARY KEY", "id SERIAL PRIMARY KEY").replace("BLOB", "BYTEA")
    with db:
        if db.postgres:
            # Duas instâncias podem acordar ao mesmo tempo; a trava evita prepararem o banco em paralelo.
            db.execute("SELECT pg_advisory_xact_lock(741201)")
        for comando in sql.split(";"):
            db.execute(comando)
        if not _tem_coluna(db, "usuarios", "trocar_senha"):
            # Bancos criados antes desta coluna: todos renovam a senha no próximo acesso.
            db.execute("ALTER TABLE usuarios ADD COLUMN trocar_senha INTEGER NOT NULL DEFAULT 0")
            db.execute("UPDATE usuarios SET trocar_senha = 1")
        if not _tem_coluna(db, "usuarios", "excluido_em"):
            db.execute("ALTER TABLE usuarios ADD COLUMN excluido_em TEXT")
        for topico in TOPICOS:
            db.execute("INSERT INTO versoes (topico) VALUES (?) ON CONFLICT DO NOTHING", (topico,))
        db.execute(
            "INSERT INTO config (chave, valor) VALUES ('esquema', ?) "
            "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
            (ESQUEMA,),
        )


def chave_secreta(db):
    """Chave das sessões: variável SECRET_KEY, ou uma gerada na primeira vez e guardada no banco."""
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    with db:
        db.execute(
            "INSERT INTO config (chave, valor) VALUES ('chave_secreta', ?) ON CONFLICT DO NOTHING",
            (secrets.token_hex(32),),
        )
    return db.execute("SELECT valor FROM config WHERE chave = 'chave_secreta'").fetchone()[0]


def apagar_tudo(db):
    tabelas = ("pagamentos", "pedido_itens", "pedidos", "comandas", "produtos", "categorias", "bordas", "mesas",
               "usuarios", "imagens", "versoes", "tentativas_login", "config")
    with db:
        for tabela in tabelas:
            db.execute(f"DROP TABLE IF EXISTS {tabela}")
