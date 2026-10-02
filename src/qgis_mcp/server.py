"""MCP server exposing the QGIS map generator as tools.

Tools are ``async`` on purpose: the SDK runs sync tools in worker threads,
while QGIS must be driven from the thread that created QgsApplication (the
main thread, where the stdio event loop runs).
"""

from __future__ import annotations

import functools
from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .catalog import LAYER_TYPES
from .session import MapSession

INSTRUCTIONS = """\
Generador de mapas temáticos con QGIS.
Flujo: 1) set_project_area con el shape (polígono) del proyecto;
2) inspect_dataset para ver campos de cada archivo si hace falta;
3) add_layer por cada capa temática (ver list_layer_types);
4) generate_map para un mapa con varias capas o generate_map_series para un
mapa por capa. Todas las capas se dibujan sobre el área del proyecto, que
siempre queda como contorno rojo encima.
"""

mcp = MCPServer("qgis-mcp", instructions=INSTRUCTIONS)
session = MapSession()


def tool(fn):
    """Register a tool whose expected errors reach the client with their message.

    The SDK hides the text of unexpected exceptions; bad paths, unknown fields
    and similar mistakes must stay readable so the model can correct them.
    """

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except (ValueError, KeyError, FileNotFoundError, RuntimeError) as exc:
            message = exc.args[0] if isinstance(exc, KeyError) and exc.args else str(exc)
            raise ToolError(message) from exc

    return mcp.tool()(wrapper)


@tool
async def list_layer_types() -> list[dict]:
    """List the thematic layers this server can style (key, title, default fields)."""
    return [lt.to_dict() for lt in LAYER_TYPES]


@tool
async def inspect_dataset(path: str) -> dict:
    """Describe a vector or raster file: CRS, extent, geometry, fields and sample values."""
    from .data import inspect
    from .qgis_env import ensure_qgis

    ensure_qgis()
    return inspect(path)


@tool
async def set_project_area(
    path: str,
    name: str | None = None,
    crs: str | None = None,
    subset: str | None = None,
) -> dict:
    """Set the project shape (polygon layer) every map is built on.

    Args:
        path: Polygon file (.shp, .gpkg, .geojson...).
        name: Project name shown on the map (defaults to the file name).
        crs: Output CRS such as "EPSG:32615"; defaults to the shape's CRS.
        subset: Optional attribute filter, e.g. "\"CODIGO\" = 'P-01'".
    """
    from .data import area_geometry, load_vector
    from .qgis_env import ensure_qgis

    ensure_qgis()
    from qgis.core import QgsCoordinateReferenceSystem

    area = session.set_area(path, name, subset)
    layer = load_vector(area.path, area.name, subset)
    target = QgsCoordinateReferenceSystem(crs) if crs else layer.crs()
    if not target.isValid():
        raise ValueError(f"Sistema de referencia inválido: {crs}")
    geom = area_geometry(layer, target)
    session.crs = crs
    return {
        "project_area": area.name,
        "crs": target.authid(),
        "area_ha": round(geom.area() / 10_000, 2) if not target.isGeographic() else None,
        "extent": [round(v, 6) for v in (geom.boundingBox().toRectF().getCoords())],
    }


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
    """Add (or replace) a thematic layer on the map.

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
    from .renderer import validate_layer

    previous = session.layers.get(layer_type)
    entry = session.add_layer(layer_type, path, field, label_field, clip, title, subset)
    try:
        details = validate_layer(entry)
    except Exception:
        if previous is not None:
            session.layers[entry.layer_type] = previous
        else:
            session.layers.pop(entry.layer_type, None)
        raise
    return {"layer_type": entry.layer_type, "title": entry.display_title, "clip": entry.clip, **details}


@tool
async def remove_layer(layer_type: str) -> dict:
    """Remove a thematic layer from the map."""
    session.remove_layer(layer_type)
    return session.to_dict()


@tool
async def reset_map() -> dict:
    """Forget the project shape and every layer added so far."""
    session.area = None
    session.crs = None
    session.layers.clear()
    return session.to_dict()


@tool
async def get_map_state() -> dict:
    """Show the project shape, output CRS and the layers added so far."""
    return session.to_dict()


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
    grid: bool = True,
    labels: bool = True,
    save_project: bool = True,
) -> dict:
    """Render one map sheet (PDF/PNG/JPG/TIF chosen by extension) over the project shape.

    Includes title, legend, north arrow, scale bar, coordinate grid and notes.
    Clipped layers are saved to a GeoPackage next to the output, and a .qgz
    project is written so the map can be edited in QGIS.

    Args:
        output_path: Where to write the map, e.g. "/salidas/mapa_general.pdf".
        layers: Layer types to include (all added layers when omitted).
        page_size: A4, A3, A2, LETTER, LEGAL or TABLOID.
        extent: "project" zooms to the project shape, "layers" to all layers.
        margin_percent: Space around the project shape, in % of its size.
        sources: Data sources credited in the notes box.
    """
    from .renderer import render_map

    return render_map(
        session,
        output_path,
        title=title,
        subtitle=subtitle,
        layer_types=layers,
        page=page_size,
        orientation=orientation,
        extent_mode=extent,
        margin_percent=margin_percent,
        dpi=dpi,
        sources=sources,
        grid=grid,
        save_project=save_project,
        labels=labels,
    )


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
) -> dict:
    """Render one map per thematic layer (e.g. Mapa de Zonas de Vida, Mapa de Cuencas...).

    Args:
        output_dir: Folder for the maps (numbered by drawing order).
        layers: Layer types to map (all added layers when omitted).
        context_layers: Layers repeated on every sheet for reference, e.g. ["rios", "vias_acceso"].
    """
    from .renderer import render_series

    return render_series(
        session,
        output_dir,
        fmt=format,
        layer_types=layers,
        context_layers=context_layers,
        page=page_size,
        orientation=orientation,
        dpi=dpi,
        sources=sources,
    )


def main() -> None:
    from .qgis_env import ensure_qgis

    ensure_qgis()
    mcp.run("stdio")


if __name__ == "__main__":
    main()
