"""MCP server exposing the QGIS map generator as tools.

By default every tool is forwarded to the QGIS MCP plugin running inside the
open QGIS (``QGIS_MCP_MODE=app``): layers appear on the canvas and each map
lands in QGIS's Layout Manager. With ``QGIS_MCP_MODE=headless`` the same
commands run in this process with PyQGIS and no QGIS window.
"""

from __future__ import annotations

import functools
import os
from typing import Any, Literal

import anyio.to_thread
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

INSTRUCTIONS = """\
Generador de mapas temáticos con QGIS.
Flujo: 1) set_project_area con el shape (polígono) del proyecto;
2) inspect_dataset para ver campos de cada archivo si hace falta;
3) add_layer por cada capa temática (ver list_layer_types);
4) generate_map para un mapa con varias capas o generate_map_series para un
mapa por capa. Todas las capas se dibujan sobre el área del proyecto, que
siempre queda como contorno rojo encima. En QGIS las capas aparecen en el
lienzo y cada mapa queda como diseño de impresión editable.
"""

mcp = MCPServer("qgis-mcp", instructions=INSTRUCTIONS)


class AppBackend:
    """Sends each command to the plugin inside the open QGIS."""

    def __init__(self, client=None):
        from .client import QgisClient

        self.client = client or QgisClient()

    async def call(self, command: str, params: dict[str, Any]) -> Any:
        from .client import QgisCommandError, QgisConnectionError

        try:
            return await anyio.to_thread.run_sync(self.client.send_command, command, params)
        except (QgisCommandError, QgisConnectionError) as exc:
            raise ToolError(str(exc)) from exc


class HeadlessBackend:
    """Runs the commands in this process with PyQGIS.

    Calls stay on the event-loop thread (the main thread, where QGIS was
    started): QGIS objects must not be driven from worker threads.
    """

    def __init__(self):
        from .commands import MapCommands

        self.commands = MapCommands()

    async def call(self, command: str, params: dict[str, Any]) -> Any:
        try:
            return self.commands.handlers()[command](**params)
        except (ValueError, KeyError, FileNotFoundError, RuntimeError) as exc:
            message = exc.args[0] if isinstance(exc, KeyError) and exc.args else str(exc)
            raise ToolError(message) from exc


def make_backend(mode: str | None = None):
    mode = (mode or os.environ.get("QGIS_MCP_MODE", "app")).lower()
    if mode == "app":
        return AppBackend()
    if mode == "headless":
        return HeadlessBackend()
    raise ValueError("QGIS_MCP_MODE debe ser 'app' o 'headless'.")


backend = None


def get_backend():
    global backend
    if backend is None:
        backend = make_backend()
    return backend


def tool(fn):
    """Register a tool that forwards its arguments to the active backend."""

    @functools.wraps(fn)
    async def wrapper(**kwargs):
        params = {k: v for k, v in kwargs.items() if v is not None}
        return await get_backend().call(fn.__name__, params)

    return mcp.tool()(wrapper)


@tool
async def ping() -> dict:
    """Check that QGIS answers and report its version."""


@tool
async def list_layer_types() -> list[dict]:
    """List the thematic layers this server can style (key, title, default fields)."""


@tool
async def inspect_dataset(path: str) -> dict:
    """Describe a vector or raster file: CRS, extent, geometry, fields and sample values."""


@tool
async def set_project_area(
    path: str,
    name: str | None = None,
    crs: str | None = None,
    subset: str | None = None,
) -> dict:
    """Set the project shape (polygon layer) every map is built on.

    In QGIS it is added on top as a red outline and the canvas zooms to it.

    Args:
        path: Polygon file (.shp, .gpkg, .geojson...).
        name: Project name shown on the map (defaults to the file name).
        crs: Output CRS such as "EPSG:32615"; defaults to the shape's CRS.
        subset: Optional attribute filter, e.g. "\"CODIGO\" = 'P-01'".
    """


@tool
async def add_layer(
    layer_type: str,
    path: str,
    field: str | None = None,
    label_field: str | None = None,
    clip: Literal["shape", "extent", "none"] | None = None,
    title: str | None = None,
    subset: str | None = None,
) -> dict:
    """Add (or replace) a thematic layer, styled from the catalog.

    In QGIS it appears in the "Capas temáticas" group, in drawing order.

    Args:
        layer_type: Key from list_layer_types, e.g. "zonas_vida", "rios", "volcanes".
        path: Vector or raster file with the data.
        field: Attribute used to classify colors (auto-detected when omitted).
        label_field: Attribute used for labels (auto-detected when omitted).
        clip: "shape" cuts to the project polygon, "extent" to the map frame,
            "none" keeps the layer whole. Defaults depend on the layer type.
        title: Legend title (defaults to the catalog title).
        subset: Optional attribute filter in QGIS expression syntax.
    """


@tool
async def remove_layer(layer_type: str) -> dict:
    """Remove a thematic layer from the map."""


@tool
async def reset_map() -> dict:
    """Forget the project shape and every layer added so far."""


@tool
async def get_map_state() -> dict:
    """Show the project shape, output CRS and the layers added so far."""


@tool
async def generate_map(
    output_path: str,
    title: str | None = None,
    subtitle: str | None = None,
    layers: list[str] | None = None,
    page_size: str = "A4",
    orientation: Literal["landscape", "portrait"] = "landscape",
    extent: Literal["project", "layers"] = "project",
    margin_percent: float = 10.0,
    dpi: int = 300,
    sources: str | None = None,
    basemap: Literal["satelite", "google", "osm"] | None = None,
    grid: bool = True,
    labels: bool = True,
    open_layout: bool = True,
) -> dict:
    """Render one map sheet (PDF/PNG/JPG/TIF chosen by extension) over the project shape.

    Includes title, legend, north arrow, scale bar, coordinate grid and notes.
    Clipped layers are saved to a GeoPackage next to the output. In QGIS the
    sheet is added to the Layout Manager (and opened when open_layout is true)
    so it can be edited there; headless, a .qgz project is saved next to it.

    Args:
        output_path: Where to write the map, e.g. "C:/salidas/mapa_general.pdf".
        layers: Layer types to include (all added layers when omitted).
        page_size: A4, A3, A2, LETTER, LEGAL or TABLOID.
        extent: "project" zooms to the project shape, "layers" to all layers.
        margin_percent: Space around the project shape, in % of its size.
        sources: Data sources credited in the notes box.
        basemap: Background under the layers: "satelite" (Esri World Imagery),
            "google" (Google Satellite) or "osm" (OpenStreetMap). Needs internet; credited in the notes.
    """


@tool
async def generate_map_series(
    output_dir: str,
    format: Literal["pdf", "png"] = "pdf",
    layers: list[str] | None = None,
    context_layers: list[str] | None = None,
    page_size: str = "A4",
    orientation: Literal["landscape", "portrait"] = "landscape",
    dpi: int = 300,
    sources: str | None = None,
    basemap: Literal["satelite", "google", "osm"] | None = None,
) -> dict:
    """Render one map per thematic layer (e.g. Mapa de Zonas de Vida, Mapa de Cuencas...).

    In QGIS each sheet is also added to the Layout Manager.

    Args:
        output_dir: Folder for the maps (numbered by drawing order).
        layers: Layer types to map (all added layers when omitted).
        context_layers: Layers repeated on every sheet for reference, e.g. ["rios", "vias_acceso"].
        basemap: "satelite", "google" or "osm" background on every sheet (needs internet).
    """


def main() -> None:
    if isinstance(get_backend(), HeadlessBackend):
        from .qgis_env import ensure_qgis

        ensure_qgis()
    mcp.run("stdio")


if __name__ == "__main__":
    main()
