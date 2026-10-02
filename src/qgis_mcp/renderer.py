"""Turn a MapSession into finished map sheets (PDF/PNG) plus a QGIS project."""

from __future__ import annotations

import re
from pathlib import Path

from .catalog import get_layer_type
from .data import (
    area_geometry,
    buffered_extent,
    clip_raster,
    clip_vector,
    layer_extent,
    load,
    load_vector,
    write_mask,
    write_to_geopackage,
)
from .layout import build_layout, default_notes, export
from .qgis_env import ensure_qgis
from .session import LayerEntry, MapSession

EXTENT_MODES = ("project", "layers")


def _slug(text: str) -> str:
    text = text.lower().translate(str.maketrans("áéíóúüñ", "aeiouun"))
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_") or "mapa"


def validate_layer(entry: LayerEntry) -> dict:
    """Open a layer and resolve its classification/label fields without rendering."""
    ensure_qgis()
    from qgis.core import QgsRasterLayer

    from .catalog import pick_field
    from .data import field_names, geometry_name

    layer = load(entry.path, entry.display_title, entry.subset)
    spec = entry.spec
    if isinstance(layer, QgsRasterLayer):
        return {"kind": "raster", "bands": layer.bandCount(), "crs": layer.crs().authid()}
    names = field_names(layer)
    for name, value in (("field", entry.field), ("label_field", entry.label_field)):
        if value is not None and value not in names:
            raise ValueError(f"El campo {value!r} no existe. Campos disponibles: {', '.join(names)}")
    geometry = geometry_name(layer)
    warnings = []
    if spec.geometry not in ("any", geometry):
        warnings.append(f"Se esperaba geometría de tipo {spec.geometry} para {spec.title} y la capa es {geometry}.")
    return {
        "kind": "vector",
        "geometry": geometry,
        "feature_count": layer.featureCount(),
        "crs": layer.crs().authid(),
        "classify_by": entry.field or (pick_field(spec.field_candidates, names) if spec.style != "single" else None),
        "label_by": entry.label_field or pick_field(spec.label_candidates, names),
        "fields": names,
        "warnings": warnings,
    }


def render_map(
    session: MapSession,
    output_path: str,
    title: str | None = None,
    subtitle: str | None = None,
    layer_types: list[str] | None = None,
    page: str = "A4",
    orientation: str = "landscape",
    extent_mode: str = "project",
    margin_percent: float = 10.0,
    dpi: int = 300,
    sources: str | None = None,
    grid: bool = True,
    save_project: bool = True,
    labels: bool = True,
) -> dict:
    """Render one map sheet with the selected layers over the project shape."""
    ensure_qgis()
    from qgis.core import QgsCoordinateReferenceSystem, QgsProject, QgsRasterLayer

    from .styling import apply_labels, style_project_area, style_raster, style_vector

    if extent_mode not in EXTENT_MODES:
        raise ValueError(f"extent debe ser uno de: {', '.join(EXTENT_MODES)}")
    area = session.require_area()
    entries = session.select(layer_types)

    out = Path(output_path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    data_dir = out.parent / f"{out.stem}_datos"
    data_dir.mkdir(exist_ok=True)
    gpkg = str(data_dir / "capas.gpkg")

    area_layer = load_vector(area.path, f"Área del proyecto: {area.name}", area.subset)
    target = QgsCoordinateReferenceSystem(session.crs) if session.crs else area_layer.crs()
    if not target.isValid():
        raise ValueError(f"Sistema de referencia inválido: {session.crs}")
    mask = area_geometry(area_layer, target)

    sources_loaded = [(entry, load(entry.path, entry.display_title, entry.subset)) for entry in entries]

    extent = buffered_extent(mask.boundingBox(), margin_percent)
    if extent_mode == "layers":
        for _, layer in sources_loaded:
            extent.combineExtentWith(layer_extent(layer, target))

    project = QgsProject()
    project.setCrs(target)
    project.setTitle(title or area.name)

    area_saved = write_to_geopackage(
        clip_vector(area_layer, target, None), gpkg, "area_proyecto"
    )
    area_saved.setName(area_layer.name())
    style_project_area(area_saved)

    rendered = []
    warnings: list[str] = []
    map_layers = []
    for entry, layer in sources_loaded:
        spec = entry.spec
        if isinstance(layer, QgsRasterLayer):
            if entry.clip == "none":
                final = layer
            else:
                mask_file = write_mask(mask, target, str(data_dir / "mascara.geojson")) if entry.clip == "shape" else None
                clipped = clip_raster(
                    entry.path, str(data_dir / f"{spec.key}.tif"), target, mask_file,
                    extent if entry.clip == "extent" else None,
                )
                final = load(clipped, entry.display_title)
            info = style_raster(final, spec)
        else:
            if entry.clip == "none":
                final = layer
            else:
                from qgis.core import QgsGeometry

                cut = mask if entry.clip == "shape" else QgsGeometry.fromRect(extent)
                final = write_to_geopackage(clip_vector(layer, target, cut), gpkg, spec.key)
                final.setName(entry.display_title)
            info = style_vector(final, spec, entry.field)
            if labels:
                info["label_field"] = apply_labels(final, spec, entry.label_field)
            info["features"] = final.featureCount()
            if final.featureCount() == 0:
                warnings.append(f"{spec.title}: ninguna entidad dentro del área del mapa.")
        warnings.extend(info.pop("warnings", []))
        project.addMapLayer(final)
        map_layers.append(final)
        rendered.append({"layer_type": spec.key, "title": entry.display_title, "clip": entry.clip, **info})

    project.addMapLayer(area_saved)
    # Map item wants top-most first; the project shape outline always stays on top.
    top_first = [area_saved, *reversed(map_layers)]
    legend_layers = top_first

    if title is None:
        title = (
            f"Mapa de {entries[0].display_title}" if len(entries) == 1 else "Mapa temático"
        )
    subtitle = subtitle if subtitle is not None else f"Proyecto: {area.name}"
    notes = default_notes(area.name, target, sources)
    layout = build_layout(
        project, top_first, legend_layers, extent, target, title, subtitle, notes, page, orientation, grid
    )
    project.layoutManager().addLayout(layout)
    exported = export(layout, str(out), dpi)

    project_path = None
    if save_project:
        project_path = str(out.with_suffix(".qgz"))
        if not project.write(project_path):
            warnings.append(f"No se pudo guardar el proyecto QGIS en {project_path}")
            project_path = None

    return {
        "output": exported,
        "project": project_path,
        "data": str(data_dir),
        "crs": target.authid(),
        "extent": [extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum()],
        "layers": rendered,
        "warnings": warnings,
    }


def render_series(
    session: MapSession,
    output_dir: str,
    fmt: str = "pdf",
    layer_types: list[str] | None = None,
    context_layers: list[str] | None = None,
    **kwargs,
) -> dict:
    """One map sheet per thematic layer, each over the project shape."""
    if fmt not in ("pdf", "png"):
        raise ValueError("format debe ser 'pdf' o 'png'.")
    entries = session.select(layer_types)
    context = [get_layer_type(name).key for name in (context_layers or [])]
    for key in context:
        if key not in session.layers:
            raise KeyError(f"La capa de contexto {key!r} no se ha agregado al mapa.")
    out_dir = Path(output_dir).expanduser()
    maps = []
    for index, entry in enumerate(entries, start=1):
        spec = entry.spec
        selection = [entry.layer_type] + [k for k in context if k != entry.layer_type]
        maps.append(
            render_map(
                session,
                str(out_dir / f"{index:02d}_{_slug(spec.key)}.{fmt}"),
                title=f"Mapa de {entry.display_title}",
                layer_types=selection,
                extent_mode="layers" if spec.extent == "layer" else "project",
                margin_percent=spec.margin_percent,
                **kwargs,
            )
        )
    return {"maps": maps, "count": len(maps)}
