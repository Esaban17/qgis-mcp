"""The plugin inside a live QGIS project, driven through its socket."""

import json
import socket
import threading

import pytest

pytestmark = pytest.mark.qgis


class FakeIface:
    def __init__(self):
        from qgis.gui import QgsMapCanvas

        self.canvas = QgsMapCanvas()
        self.opened = []

    def mapCanvas(self):  # noqa: N802
        return self.canvas

    def openLayoutDesigner(self, layout):  # noqa: N802
        self.opened.append(layout.name())


@pytest.fixture()
def plugin(qgis_app):
    from qgis.core import QgsProject

    from qgis_mcp.plugin import QgisMcpPlugin

    QgsProject.instance().clear()
    plug = QgisMcpPlugin(FakeIface(), port=0)
    yield plug
    plug.stop()
    QgsProject.instance().clear()


def _send(plugin, command, **params):
    """Talk to the plugin over TCP while QGIS's event loop runs on this thread."""
    from qgis.PyQt.QtCore import QCoreApplication, QEventLoop

    if plugin.server is None:
        assert plugin.start()
    port = plugin.server.serverPort()
    reply = {}

    def client():
        with socket.create_connection(("127.0.0.1", port), timeout=60) as sock:
            sock.sendall((json.dumps({"command": command, "params": params}) + "\n").encode())
            data = b""
            while not data.endswith(b"\n"):
                chunk = sock.recv(65536)
                if not chunk:
                    break
                data += chunk
        reply["message"] = json.loads(data)

    thread = threading.Thread(target=client, daemon=True)
    thread.start()
    while thread.is_alive():
        QCoreApplication.processEvents(QEventLoop.AllEvents, 50)
    message = reply["message"]
    if message["status"] != "ok":
        raise RuntimeError(message["message"])
    return message["result"]


def test_ping_over_socket(plugin):
    assert _send(plugin, "ping")["live"] is True


def test_unknown_command_and_errors_come_back_as_messages(plugin):
    with pytest.raises(RuntimeError, match="Orden desconocida"):
        _send(plugin, "borrar_todo")
    with pytest.raises(RuntimeError, match="Tipo de capa desconocido"):
        _send(plugin, "remove_layer", layer_type="geologia")


def test_layers_show_up_in_the_open_project(plugin, sample, tmp_path):
    from qgis.core import QgsProject

    project = QgsProject.instance()
    _send(plugin, "set_project_area", path=sample["area"], name="Proyecto Demo")
    for key in ("rios", "zonas_vida", "volcanes"):
        _send(plugin, "add_layer", layer_type=key, path=sample[key])

    root = project.layerTreeRoot()
    top = [node.name() for node in root.children()]
    assert top[:2] == ["Área del proyecto: Proyecto Demo", "Capas temáticas"]
    group = root.findGroup("Capas temáticas")
    assert [n.name() for n in group.children()] == ["Volcanes", "Ríos", "Zonas de Vida"]
    assert not plugin.iface.canvas.extent().isEmpty()

    # Replacing a layer keeps a single copy in the project.
    _send(plugin, "add_layer", layer_type="rios", path=sample["rios"], title="Red hídrica")
    assert [n.name() for n in group.children()] == ["Volcanes", "Red hídrica", "Zonas de Vida"]

    result = _send(plugin, "generate_map", output_path=str(tmp_path / "general.pdf"), title="Mapa general", dpi=60)
    assert (tmp_path / "general.pdf").exists()
    assert result["project"] is None
    assert project.layoutManager().layoutByName("Mapa general") is not None
    assert plugin.iface.opened == ["Mapa general"]
    map_group = root.findGroup("Mapa: Mapa general")
    assert map_group is not None and not map_group.itemVisibilityChecked()

    # Generating the same map again replaces it instead of piling up copies.
    _send(plugin, "generate_map", output_path=str(tmp_path / "general.pdf"), title="Mapa general", dpi=60, open_layout=False)
    assert sum(1 for g in root.children() if g.name() == "Mapa: Mapa general") == 1
    assert len(project.layoutManager().printLayouts()) == 1

    _send(plugin, "remove_layer", layer_type="volcanes")
    assert [n.name() for n in group.children()] == ["Red hídrica", "Zonas de Vida"]
    _send(plugin, "reset_map")
    # The shape and thematic layers go; the generated map (group + layout) stays.
    assert [n.name() for n in root.children()] == ["Capas temáticas", "Mapa: Mapa general"]
    assert group.children() == []


def test_series_adds_one_layout_per_layer(plugin, sample, tmp_path):
    from qgis.core import QgsProject

    _send(plugin, "set_project_area", path=sample["area"], name="Proyecto Demo")
    _send(plugin, "add_layer", layer_type="cuencas", path=sample["cuencas"])
    _send(plugin, "add_layer", layer_type="uso_suelo", path=sample["uso_suelo"])
    out = _send(plugin, "generate_map_series", output_dir=str(tmp_path / "serie"), format="png", dpi=40)
    assert out["count"] == 2
    names = sorted(layout.name() for layout in QgsProject.instance().layoutManager().printLayouts())
    assert names == ["Mapa de Cuencas Hidrográficas", "Mapa de Uso de Suelo"]


def test_install_plugin_copies_package(tmp_path):
    from qgis_mcp.install_plugin import install

    target = install(tmp_path)
    assert (target / "metadata.txt").exists()
    assert (target / "__init__.py").read_text().count("classFactory") >= 1
    assert not list(target.rglob("__pycache__"))
