import sqlite3
from datetime import datetime

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL,
    usuario TEXT NOT NULL UNIQUE,
    senha_hash TEXT NOT NULL,
    perfil TEXT NOT NULL CHECK (perfil IN ('admin', 'garcom', 'cozinha')),
    ativo INTEGER NOT NULL DEFAULT 1
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
"""


def agora():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def conectar(caminho):
    con = sqlite3.connect(caminho, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    return con


def criar_tabelas(con):
    con.executescript(SCHEMA)
    con.commit()


def get_db():
    if "db" not in g:
        g.db = conectar(current_app.config["BANCO"])
    return g.db


def fechar_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()
