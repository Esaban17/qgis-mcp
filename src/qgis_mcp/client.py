"""Cliente del socket que expone el plugin de QGIS.

Protocolo: una línea JSON por mensaje.
  Petición:  {"command": "<nombre>", "params": {...}}
  Respuesta: {"status": "ok", "result": ...} o {"status": "error", "message": "..."}
"""

from __future__ import annotations

import json
import os
import socket
from typing import Any

DEFAULT_HOST = os.environ.get("QGIS_MCP_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("QGIS_MCP_PORT", "9876"))
DEFAULT_TIMEOUT = float(os.environ.get("QGIS_MCP_TIMEOUT", "600"))


class QgisConnectionError(RuntimeError):
    """No se pudo hablar con el plugin de QGIS."""


class QgisCommandError(RuntimeError):
    """El plugin de QGIS ejecutó la orden pero devolvió un error."""


class QgisClient:
    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout

    def send_command(self, command: str, params: dict[str, Any] | None = None) -> Any:
        payload = json.dumps({"command": command, "params": params or {}}) + "\n"
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
                sock.sendall(payload.encode("utf-8"))
                response = _read_line(sock)
        except OSError as exc:
            raise QgisConnectionError(
                f"No se pudo conectar con QGIS en {self.host}:{self.port}. "
                "Abre QGIS y activa el plugin 'QGIS MCP'."
            ) from exc

        try:
            message = json.loads(response)
        except json.JSONDecodeError as exc:
            raise QgisCommandError(f"Respuesta inválida de QGIS: {response!r}") from exc

        if message.get("status") != "ok":
            raise QgisCommandError(message.get("message", "Error desconocido en QGIS"))
        return message.get("result")


def _read_line(sock: socket.socket) -> str:
    chunks: list[bytes] = []
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            break
        chunks.append(chunk)
        if chunk.endswith(b"\n"):
            break
    if not chunks:
        raise OSError("QGIS cerró la conexión sin responder")
    return b"".join(chunks).decode("utf-8").strip()
