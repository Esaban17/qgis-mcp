import asyncio
import json
import socket
import threading

import pytest

from qgis_mcp.client import QgisClient, QgisCommandError, QgisConnectionError


def _serve_once(response: dict):
    """Levanta un socket que responde una vez, como lo haría el plugin."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    received = {}

    def run():
        conn, _ = server.accept()
        with conn:
            data = b""
            while not data.endswith(b"\n"):
                data += conn.recv(4096)
            received["request"] = json.loads(data)
            conn.sendall((json.dumps(response) + "\n").encode())
        server.close()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return server.getsockname()[1], received, thread


def test_send_command_returns_result():
    port, received, thread = _serve_once({"status": "ok", "result": "pong"})
    result = QgisClient(port=port, timeout=5).send_command("ping")
    thread.join(5)
    assert result == "pong"
    assert received["request"] == {"command": "ping", "params": {}}


def test_send_command_passes_params():
    port, received, thread = _serve_once({"status": "ok", "result": {"id": "x"}})
    QgisClient(port=port, timeout=5).send_command("add_layer", {"path": "/datos/rios.shp"})
    thread.join(5)
    assert received["request"]["params"] == {"path": "/datos/rios.shp"}


def test_error_response_raises():
    port, _, thread = _serve_once({"status": "error", "message": "No existe la capa: rios"})
    with pytest.raises(QgisCommandError, match="No existe la capa"):
        QgisClient(port=port, timeout=5).send_command("remove_layer", {"layer": "rios"})
    thread.join(5)


def test_connection_refused_raises():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    with pytest.raises(QgisConnectionError, match="QGIS MCP"):
        QgisClient(port=port, timeout=1).send_command("ping")


def test_server_exposes_tools():
    from qgis_mcp.server import mcp

    names = {tool.name for tool in asyncio.run(mcp.list_tools())}
    assert {
        "ping",
        "get_project_info",
        "load_project_shape",
        "add_layer",
        "list_layers",
        "remove_layer",
        "zoom_to_project",
        "export_map",
        "save_project",
    } <= names
