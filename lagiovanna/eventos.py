"""Avisos de mudança entre as telas.

Cada assunto (pedidos, mesas, cardápio, caixa) tem um contador no banco. Quem muda algo soma um;
as telas consultam os contadores a cada poucos segundos e recarregam só o que mudou. Funciona com
qualquer número de instâncias do servidor, inclusive em hospedagem sem conexões longas.
"""
from .db import get_db


def publicar(*topicos):
    db = get_db()
    marcas = ",".join("?" * len(topicos))
    with db:
        db.execute(f"UPDATE versoes SET numero = numero + 1 WHERE topico IN ({marcas})", topicos)


def versoes(db):
    return {linha["topico"]: linha["numero"] for linha in db.execute("SELECT topico, numero FROM versoes")}
