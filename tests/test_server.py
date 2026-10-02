import asyncio
import json
import socket
import threading

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from qgis_mcp import server

TOOLS = {
    "ping", "list_layer_types", "inspect_dataset", "set_project_area", "add_layer", "set_basemap", "remove_layer",
    "reset_map", "get_map_state", "generate_map", "generate_map_series",
}


def _call(tool_name, **arguments):
    result = asyncio.run(server.mcp.call_tool(tool_name, arguments))
    assert not result.is_error, result.content[0].text
    data = result.structured_content or json.loads(result.content[0].text)
    return data.get("result", data) if isinstance(data, dict) and set(data) == {"result"} else data


def _serve_once(response: dict):
    """A socket that answers one request, like the plugin does."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    received = {}

    def run():
        conn, _ = listener.accept()
        with conn:
            data = b""
            while not data.endswith(b"\n"):
                data += conn.recv(4096)
            received["request"] = json.loads(data)
            conn.sendall((json.dumps(response) + "\n").encode())
        listener.close()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return listener.getsockname()[1], received, thread


@pytest.fixture()
def app_backend(monkeypatch):
    def use(port):
        from qgis_mcp.client import QgisClient

        monkeypatch.setattr(server, "backend", server.AppBackend(QgisClient(port=port, timeout=5)))

    return use


@pytest.fixture()
def headless(monkeypatch):
    monkeypatch.setattr(server, "backend", server.HeadlessBackend())
    return server.backend


def test_server_exposes_tools():
    assert TOOLS <= {tool.name for tool in asyncio.run(server.mcp.list_tools())}


def test_default_mode_talks_to_qgis(monkeypatch):
    monkeypatch.delenv("QGIS_MCP_MODE", raising=False)
    assert isinstance(server.make_backend(), server.AppBackend)
    with pytest.raises(ValueError):
        server.make_backend("otro")


def test_tool_forwards_arguments_to_plugin(app_backend):
    port, received, thread = _serve_once({"status": "ok", "result": {"layer_type": "rios"}})
    app_backend(port)
    out = _call("add_layer", layer_type="rios", path="C:/datos/rios.shp")
    thread.join(5)
    assert out["layer_type"] == "rios"
    assert received["request"] == {
        "command": "add_layer",
        "params": {"layer_type": "rios", "path": "C:/datos/rios.shp"},
    }


def test_plugin_error_reaches_the_model(app_backend):
    port, _, thread = _serve_once({"status": "error", "message": "El campo 'NADA' no existe"})
    app_backend(port)
    with pytest.raises(ToolError, match="NADA"):
        asyncio.run(server.mcp.call_tool("add_layer", {"layer_type": "rios", "path": "x.shp", "field": "NADA"}))
    thread.join(5)


def test_qgis_closed_gives_clear_message(app_backend):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    app_backend(port)
    with pytest.raises(ToolError, match="Abre QGIS"):
        asyncio.run(server.mcp.call_tool("ping", {}))


def test_list_layer_types_headless(headless):
    assert len(_call("list_layer_types")) == 15


@pytest.mark.qgis
def test_end_to_end_headless(headless, sample, tmp_path):
    area = _call("set_project_area", path=sample["area"], name="Proyecto Demo")
    assert area["crs"] == "EPSG:32615" and area["area_ha"] > 0
    added = _call("add_layer", layer_type="Zonas de Vida", path=sample["zonas_vida"])
    assert added["classify_by"] == "ZONA_VIDA"
    _call("add_layer", layer_type="volcanes", path=sample["volcanes"])
    state = _call("get_map_state")
    assert [layer["layer_type"] for layer in state["layers"]] == ["zonas_vida", "volcanes"]
    out = _call("generate_map", output_path=str(tmp_path / "mapa.pdf"), dpi=60)
    assert out["output"].endswith("mapa.pdf") and out["project"].endswith("mapa.qgz")


@pytest.mark.qgis
def test_add_layer_rolls_back_on_bad_field(headless, sample):
    with pytest.raises(ToolError, match="NADA"):
        asyncio.run(server.mcp.call_tool("add_layer", {"layer_type": "Ríos", "path": sample["rios"], "field": "NADA"}))
    assert "rios" not in headless.commands.session.layers
