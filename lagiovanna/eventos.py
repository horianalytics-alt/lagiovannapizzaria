"""Canal de eventos em memória para as telas se atualizarem em tempo real (SSE)."""
import queue
import threading


class Canal:
    def __init__(self):
        self._assinantes = set()
        self._trava = threading.Lock()

    def assinar(self):
        fila = queue.Queue(maxsize=200)
        with self._trava:
            self._assinantes.add(fila)
        return fila

    def cancelar(self, fila):
        with self._trava:
            self._assinantes.discard(fila)

    def publicar(self, *tipos):
        with self._trava:
            assinantes = list(self._assinantes)
        for fila in assinantes:
            for tipo in tipos:
                try:
                    fila.put_nowait(tipo)
                except queue.Full:
                    pass


canal = Canal()


def fluxo_sse(intervalo_ping=15):
    fila = canal.assinar()
    try:
        yield "retry: 2000\n\n"
        while True:
            try:
                tipo = fila.get(timeout=intervalo_ping)
                yield f"data: {tipo}\n\n"
            except queue.Empty:
                yield ": ping\n\n"
    finally:
        canal.cancelar(fila)
