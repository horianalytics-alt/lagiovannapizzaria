"""Inicia o sistema da La Giovanna.  Uso:  python app.py  [--porta 5000] [--reiniciar-demo]"""
import argparse
import os
import socket
from pathlib import Path

from lagiovanna import RAIZ, create_app


def _ip_da_rede():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return None


def main():
    opcoes = argparse.ArgumentParser(description="Sistema da pizzaria La Giovanna")
    opcoes.add_argument("--porta", type=int, default=int(os.environ.get("PORT", 5000)))
    opcoes.add_argument("--reiniciar-demo", action="store_true", help="apaga o banco e recria os dados de demonstração")
    args = opcoes.parse_args()

    pasta = Path(os.environ.get("LAGIOVANNA_DADOS") or RAIZ / "dados")
    if args.reiniciar_demo:
        for sufixo in ("", "-wal", "-shm"):
            (pasta / f"lagiovanna.db{sufixo}").unlink(missing_ok=True)
        print("Banco apagado. Recriando os dados de demonstração...")

    app = create_app(pasta)

    from waitress import serve

    print(f"\n  La Giovanna no ar:  http://localhost:{args.porta}")
    ip = _ip_da_rede()
    if ip and not ip.startswith("127."):
        print(f"  Na rede (celulares): http://{ip}:{args.porta}")
    print("  Para parar: Ctrl+C\n")
    # Cada tela aberta mantém uma conexão de eventos; por isso o número alto de threads.
    serve(app, host="0.0.0.0", port=args.porta, threads=96, connection_limit=400, channel_timeout=120)


if __name__ == "__main__":
    main()
