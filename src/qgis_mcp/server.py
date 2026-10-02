"""Herramientas MCP que controlan QGIS a través del plugin."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from .client import QgisClient

mcp = FastMCP("qgis-mcp")
client = QgisClient()


@mcp.tool()
def ping() -> Any:
    """Comprueba que QGIS está abierto y el plugin escuchando."""
    return client.send_command("ping")


@mcp.tool()
def get_project_info() -> Any:
    """Devuelve el CRS, la ruta del proyecto y las capas cargadas en QGIS."""
    return client.send_command("get_project_info")


@mcp.tool()
def load_project_shape(path: str, name: str = "Área del proyecto") -> Any:
    """Carga el shape del proyecto como capa base y centra el mapa en él.

    Las capas temáticas que se agreguen después quedan encima de este shape.
    """
    return client.send_command("load_project_shape", {"path": path, "name": name})


@mcp.tool()
def add_layer(path: str, name: str | None = None, style_path: str | None = None) -> Any:
    """Agrega una capa vectorial o ráster encima del shape del proyecto.

    El tipo se detecta por la extensión (.tif, .tiff, .img, .asc, .vrt son ráster).
    style_path es opcional y apunta a un archivo de estilo .qml.
    """
    return client.send_command(
        "add_layer", {"path": path, "name": name, "style_path": style_path}
    )


@mcp.tool()
def list_layers() -> Any:
    """Lista las capas del proyecto en orden de dibujo (de arriba hacia abajo)."""
    return client.send_command("list_layers")


@mcp.tool()
def remove_layer(layer: str) -> Any:
    """Quita una capa por su id o su nombre."""
    return client.send_command("remove_layer", {"layer": layer})


@mcp.tool()
def zoom_to_project(margin_percent: float = 10.0) -> Any:
    """Centra el mapa en el shape del proyecto con un margen alrededor."""
    return client.send_command("zoom_to_project", {"margin_percent": margin_percent})


@mcp.tool()
def export_map(
    output_path: str,
    title: str = "",
    dpi: int = 300,
    margin_percent: float = 10.0,
) -> Any:
    """Exporta el mapa a PDF o PNG (según la extensión de output_path).

    Usa un layout A4 horizontal con título, leyenda y escala, encuadrado en el
    shape del proyecto.
    """
    return client.send_command(
        "export_map",
        {
            "output_path": output_path,
            "title": title,
            "dpi": dpi,
            "margin_percent": margin_percent,
        },
    )


@mcp.tool()
def save_project(path: str | None = None) -> Any:
    """Guarda el proyecto de QGIS (.qgz). Sin ruta, guarda sobre el actual."""
    return client.send_command("save_project", {"path": path})


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
