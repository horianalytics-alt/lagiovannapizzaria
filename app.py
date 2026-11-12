"""Sistema da La Giovanna.

No computador:  python app.py  [--porta 5000] [--reiniciar-demo]
Na Vercel:      a plataforma importa a variável `app` deste arquivo.
"""
import argparse
import os
import socket
import sys

from lagiovanna import banco_configurado, create_app
from lagiovanna.db import abrir, apagar_tudo


def _ip_da_rede():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return None


def _reiniciar_demo():
    tipo, alvo = banco_configurado()
    if tipo == "postgres":
        print("ATENÇÃO: isto apaga TODOS os dados do banco na nuvem (pedidos, cardápio, equipe).")
        if input('Digite APAGAR para confirmar: ').strip() != "APAGAR":
            sys.exit("Nada foi apagado.")
    db = abrir(tipo, alvo)
    apagar_tudo(db)
    db.close()
    print("Banco apagado. Recriando os dados de demonstração...")


def main():
    opcoes = argparse.ArgumentParser(description="Sistema da pizzaria La Giovanna")
    opcoes.add_argument("--porta", type=int, default=int(os.environ.get("PORT", 5000)))
    opcoes.add_argument("--reiniciar-demo", action="store_true", help="apaga o banco e recria os dados de demonstração")
    args = opcoes.parse_args()

    from waitress import serve

    print(f"\n  La Giovanna no ar:  http://localhost:{args.porta}")
    ip = _ip_da_rede()
    if ip and not ip.startswith("127."):
        print(f"  Na rede (celulares): http://{ip}:{args.porta}")
    print("  Para parar: Ctrl+C\n")
    serve(app, host="0.0.0.0", port=args.porta, threads=16)


if __name__ == "__main__" and "--reiniciar-demo" in sys.argv:
    _reiniciar_demo()

app = create_app()

if __name__ == "__main__":
    main()
