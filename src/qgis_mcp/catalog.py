"""Catalog of the thematic layers the map generator knows how to style.

This module is pure Python (no QGIS imports) so it can be inspected and
tested without a QGIS installation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Geometry = Literal["point", "line", "polygon", "any"]
StyleKind = Literal["single", "categorized", "graduated"]
ClipMode = Literal["shape", "extent", "none"]
ExtentMode = Literal["project", "layer"]


@dataclass(frozen=True)
class LayerType:
    """Default rendering rules for one thematic layer."""

    key: str
    title: str
    description: str
    geometry: Geometry
    style: StyleKind
    # Base color for single-symbol rendering (and outlines).
    color: str
    # Colors used, in order, for categories / graduated ramps.
    palette: tuple[str, ...] = ()
    # Attribute names tried (case-insensitive) to classify the layer.
    field_candidates: tuple[str, ...] = ()
    # Attribute names tried (case-insensitive) to label features.
    label_candidates: tuple[str, ...] = ()
    # Polygon fill opacity, 0..1.
    opacity: float = 1.0
    # Line width (mm) for lines and polygon outlines.
    width: float = 0.26
    # Marker size (mm) for points.
    size: float = 2.5
    # Marker shape for points (QGIS simple marker shape names).
    marker: str = "circle"
    # Drawing order: higher values are drawn on top.
    z: int = 10
    # How the layer is cut to the project shape by default.
    clip: ClipMode = "shape"
    # What a single-layer map of this theme is zoomed to by default.
    extent: ExtentMode = "project"
    # Margin around the project shape, as a percentage of its size.
    margin_percent: float = 10.0
    aliases: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "title": self.title,
            "description": self.description,
            "geometry": self.geometry,
            "style": self.style,
            "field_candidates": list(self.field_candidates),
            "label_candidates": list(self.label_candidates),
            "default_clip": self.clip,
            "default_extent": self.extent,
            "aliases": list(self.aliases),
        }


_NAME_FIELDS = ("NOMBRE", "NAME", "NOM", "NOMBRE_1", "LABEL")

LAYER_TYPES: tuple[LayerType, ...] = (
    LayerType(
        key="ubicacion",
        title="Ubicación",
        description="Contexto político-administrativo (país, departamentos, municipios) para el mapa de ubicación.",
        geometry="any",
        style="single",
        color="#f2efe6",
        label_candidates=("MUNICIPIO", "DEPARTAMEN", "DEPARTAMENTO", *_NAME_FIELDS),
        width=0.3,
        z=1,
        clip="none",
        extent="layer",
        aliases=("location", "localizacion", "municipios", "departamentos"),
    ),
    LayerType(
        key="rios",
        title="Ríos",
        description="Red hídrica (ríos, quebradas, riachuelos).",
        geometry="line",
        style="single",
        color="#2b7bba",
        label_candidates=("RIO", "NOMBRE_RIO", *_NAME_FIELDS),
        width=0.35,
        z=60,
        aliases=("rivers", "red_hidrica", "hidrografia"),
    ),
    LayerType(
        key="zonas_vida",
        title="Zonas de Vida",
        description="Zonas de vida según el sistema de Holdridge.",
        geometry="polygon",
        style="categorized",
        color="#5a8f3d",
        palette=("#1a9850", "#66bd63", "#a6d96a", "#d9ef8b", "#fee08b", "#fdae61", "#f46d43", "#d73027", "#91cf60", "#3288bd"),
        field_candidates=("ZONA_VIDA", "ZONAVIDA", "ZV", "SIMBOLO", "DESCRIPCIO", "DESCRIPCION", *_NAME_FIELDS),
        opacity=0.75,
        z=20,
        aliases=("life_zones", "holdridge", "zonas_de_vida"),
    ),
    LayerType(
        key="vias_acceso",
        title="Vías de Acceso",
        description="Carreteras, caminos y veredas de acceso.",
        geometry="line",
        style="categorized",
        color="#7f2704",
        palette=("#d7301f", "#fc8d59", "#fdcc8a", "#737373", "#252525"),
        field_candidates=("TIPO", "TIPO_VIA", "CLASE", "CATEGORIA", "RODADURA", "SUPERFICIE"),
        label_candidates=("RUTA", "CODIGO", *_NAME_FIELDS),
        width=0.5,
        z=70,
        aliases=("roads", "vias", "carreteras", "caminos"),
    ),
    LayerType(
        key="cuencas",
        title="Cuencas Hidrográficas",
        description="Cuencas, subcuencas y microcuencas hidrográficas.",
        geometry="polygon",
        style="categorized",
        color="#08519c",
        palette=("#c6dbef", "#9ecae1", "#6baed6", "#deebf7", "#c7e9c0", "#a1d99b", "#fdd0a2", "#dadaeb"),
        field_candidates=("CUENCA", "SUBCUENCA", "MICROCUENC", "MICROCUENCA", *_NAME_FIELDS),
        label_candidates=("CUENCA", "SUBCUENCA", *_NAME_FIELDS),
        opacity=0.55,
        width=0.6,
        z=15,
        aliases=("watersheds", "basins", "cuencas_hidrograficas"),
    ),
    LayerType(
        key="cuerpos_agua",
        title="Cuerpos de Agua",
        description="Lagos, lagunas, embalses y otros cuerpos de agua.",
        geometry="polygon",
        style="single",
        color="#6baed6",
        label_candidates=_NAME_FIELDS,
        opacity=0.9,
        z=55,
        aliases=("water_bodies", "lagos", "lagunas"),
    ),
    LayerType(
        key="areas_protegidas",
        title="Áreas Protegidas",
        description="Áreas protegidas (SIGAP / CONAP) y sus categorías de manejo.",
        geometry="polygon",
        style="categorized",
        color="#238b45",
        palette=("#41ab5d", "#74c476", "#a1d99b", "#00441b", "#006d2c", "#c7e9c0"),
        field_candidates=("CATEGORIA", "CAT_MANEJO", "CATEGORIA_", *_NAME_FIELDS),
        label_candidates=_NAME_FIELDS,
        opacity=0.45,
        width=0.6,
        z=40,
        aliases=("protected_areas", "sigap", "conap"),
    ),
    LayerType(
        key="temperatura_thornthwaite",
        title="Temperatura (Thornthwaite)",
        description="Caracterización de la temperatura según el sistema de Thornthwaite.",
        geometry="polygon",
        style="categorized",
        color="#d94801",
        palette=("#313695", "#4575b4", "#74add1", "#abd9e9", "#fee090", "#fdae61", "#f46d43", "#d73027", "#a50026"),
        field_candidates=("TEMPERATUR", "TEMPERATURA", "TEMP", "CLASE", "SIMBOLO", "DESCRIPCIO"),
        opacity=0.75,
        z=25,
        aliases=("temperature", "temperatura"),
    ),
    LayerType(
        key="precipitacion_media",
        title="Precipitación Media Anual",
        description="Precipitación media anual (mm), en polígonos de rangos, isoyetas o ráster.",
        geometry="any",
        style="graduated",
        color="#2171b5",
        palette=("#f7fbff", "#08306b"),
        field_candidates=("PRECIPITAC", "PRECIPITACION", "PP", "PRECIP", "MM", "RANGO", "VALOR"),
        label_candidates=("PRECIPITAC", "PRECIPITACION", "PP", "MM"),
        opacity=0.75,
        z=25,
        aliases=("precipitation", "precipitacion", "isoyetas", "lluvia"),
    ),
    LayerType(
        key="humedad_thornthwaite",
        title="Humedad (Thornthwaite)",
        description="Clasificación de humedad según el sistema de Thornthwaite.",
        geometry="polygon",
        style="categorized",
        color="#41ab5d",
        palette=("#8c510a", "#d8b365", "#f6e8c3", "#c7eae5", "#5ab4ac", "#01665e", "#003c30"),
        field_candidates=("HUMEDAD", "CLASE", "SIMBOLO", "DESCRIPCIO", "TIPO"),
        opacity=0.75,
        z=25,
        aliases=("humidity", "humedad", "clasificacion_humedad"),
    ),
    LayerType(
        key="indice_humedad",
        title="Índice de Humedad",
        description="Índice de humedad (Im) de Thornthwaite.",
        geometry="any",
        style="graduated",
        color="#01665e",
        palette=("#a6611a", "#018571"),
        field_candidates=("INDICE", "IH", "IM", "INDICE_HUM", "VALOR", "RANGO"),
        opacity=0.75,
        z=25,
        aliases=("moisture_index", "indice", "im"),
    ),
    LayerType(
        key="taxonomia_suelos",
        title="Taxonomía de Suelos",
        description="Órdenes y subórdenes de suelo (USDA Soil Taxonomy).",
        geometry="polygon",
        style="categorized",
        color="#8c510a",
        palette=("#8c510a", "#bf812d", "#dfc27d", "#f6e8c3", "#c7a27c", "#a6611a", "#e6ab02", "#7f3b08", "#b35806", "#fdb863", "#d9d9d9", "#969696"),
        field_candidates=("ORDEN", "SUBORDEN", "TAXONOMIA", "ORDEN_SUEL", "CLASE", *_NAME_FIELDS),
        opacity=0.75,
        z=20,
        aliases=("soil_taxonomy", "suelos", "taxonomia"),
    ),
    LayerType(
        key="uso_suelo",
        title="Uso de Suelo",
        description="Cobertura vegetal y uso de la tierra.",
        geometry="polygon",
        style="categorized",
        color="#e6ab02",
        palette=("#33a02c", "#b2df8a", "#ffff99", "#fdbf6f", "#ff7f00", "#e31a1c", "#a6cee3", "#1f78b4", "#cab2d6", "#6a3d9a", "#b15928", "#bdbdbd"),
        field_candidates=("USO", "USO_SUELO", "COBERTURA", "CATEGORIA", "CLASE", "DESCRIPCIO"),
        opacity=0.75,
        z=20,
        aliases=("land_use", "uso", "cobertura"),
    ),
    LayerType(
        key="comunidades",
        title="Comunidades",
        description="Centros poblados, aldeas, caseríos y comunidades identificadas.",
        geometry="point",
        style="single",
        color="#000000",
        label_candidates=("COMUNIDAD", "LUGAR_POBL", "POBLADO", *_NAME_FIELDS),
        size=2.2,
        marker="circle",
        z=90,
        clip="extent",
        aliases=("communities", "poblados", "centros_poblados", "aldeas"),
    ),
    LayerType(
        key="volcanes",
        title="Volcanes",
        description="Volcanes de la región del proyecto.",
        geometry="point",
        style="single",
        color="#b30000",
        label_candidates=("VOLCAN", *_NAME_FIELDS),
        size=4.0,
        marker="triangle",
        z=95,
        clip="none",
        # Zoom to every volcano in the file: a fixed margin around a small
        # project leaves volcanoes tens of km away off the sheet.
        extent="layer",
        margin_percent=150.0,
        aliases=("volcanoes", "volcan"),
    ),
)

_BY_KEY = {lt.key: lt for lt in LAYER_TYPES}
_BY_ALIAS = {alias: lt for lt in LAYER_TYPES for alias in (lt.key, *lt.aliases)}


def _normalize(name: str) -> str:
    replacements = str.maketrans("áéíóúüñ", "aeiouun")
    return name.strip().lower().translate(replacements).replace(" ", "_").replace("-", "_")


def get_layer_type(name: str) -> LayerType:
    """Look a layer type up by key or alias (accents and case are ignored)."""
    norm = _normalize(name)
    if norm in _BY_ALIAS:
        return _BY_ALIAS[norm]
    raise KeyError(
        f"Tipo de capa desconocido: {name!r}. Tipos válidos: {', '.join(_BY_KEY)}"
    )


def pick_field(candidates: tuple[str, ...], available: list[str]) -> str | None:
    """Return the first available attribute matching a candidate, ignoring case."""
    lookup = {name.upper(): name for name in available}
    for candidate in candidates:
        if candidate.upper() in lookup:
            return lookup[candidate.upper()]
    return None
