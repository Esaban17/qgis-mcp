"""Apply the catalog's default symbology and labels to QGIS layers."""

from __future__ import annotations

import re

from qgis.core import (
    QgsCategorizedSymbolRenderer,
    QgsClassificationJenks,
    QgsColorRampShader,
    QgsFillSymbol,
    QgsGradientColorRamp,
    QgsGraduatedSymbolRenderer,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsRasterBandStats,
    QgsRasterLayer,
    QgsRasterShader,
    QgsRendererCategory,
    QgsSingleBandPseudoColorRenderer,
    QgsSingleSymbolRenderer,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor, QFont

from .catalog import LayerType, pick_field

MAX_CATEGORIES = 40
PROJECT_AREA_COLOR = "#e31a1c"


def _color(hex_color: str, alpha: float = 1.0) -> QColor:
    color = QColor(hex_color)
    color.setAlphaF(alpha)
    return color


def _rgba(color: QColor) -> str:
    return f"{color.red()},{color.green()},{color.blue()},{color.alpha()}"


def palette_colors(palette: tuple[str, ...], count: int) -> list[QColor]:
    """``count`` distinct colors: the palette first, then generated hues."""
    colors = [QColor(c) for c in palette[:count]]
    hue = 0.13
    while len(colors) < count:
        hue = (hue + 0.618033988749895) % 1.0
        colors.append(QColor.fromHsvF(hue, 0.45, 0.9))
    return colors


def make_symbol(spec: LayerType, geometry_type, fill: QColor | None = None):
    fill = fill or QColor(spec.color)
    if geometry_type == QgsWkbTypes.PointGeometry:
        return QgsMarkerSymbol.createSimple(
            {
                "name": spec.marker,
                "color": _rgba(fill),
                "outline_color": "255,255,255,255",
                "outline_width": "0.2",
                "size": str(spec.size),
            }
        )
    if geometry_type == QgsWkbTypes.LineGeometry:
        return QgsLineSymbol.createSimple(
            {"line_color": _rgba(fill), "line_width": str(spec.width), "capstyle": "round"}
        )
    fill_color = QColor(fill)
    fill_color.setAlphaF(spec.opacity)
    outline = QColor(fill).darker(150)
    return QgsFillSymbol.createSimple(
        {
            "color": _rgba(fill_color),
            "outline_color": _rgba(outline),
            "outline_width": str(spec.width if spec.style == "single" else 0.15),
        }
    )


def _natural_key(value) -> list:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", str(value))]


def _is_numeric(layer: QgsVectorLayer, field: str) -> bool:
    fld = layer.fields().field(field)
    return fld.isNumeric() or fld.type() in (QVariant.Int, QVariant.Double, QVariant.LongLong)


def style_vector(layer: QgsVectorLayer, spec: LayerType, field: str | None = None) -> dict:
    """Style a vector layer; returns how it was classified."""
    geom = layer.geometryType()
    available = [f.name() for f in layer.fields()]
    warnings: list[str] = []

    if field is not None and field not in available:
        raise ValueError(f"El campo {field!r} no existe en {layer.name()}. Campos: {', '.join(available)}")
    if field is None and spec.style != "single":
        field = pick_field(spec.field_candidates, available)
        if field is None:
            warnings.append(
                f"No se encontró un campo para clasificar {spec.title} "
                f"(se buscó: {', '.join(spec.field_candidates)}); se usa un solo color."
            )

    style = spec.style if field else "single"
    if style == "graduated" and not _is_numeric(layer, field):
        style = "categorized"

    info: dict = {"style": style, "field": field, "warnings": warnings}
    if style == "categorized":
        index = layer.fields().indexOf(field)
        values = sorted(
            (v for v in layer.uniqueValues(index) if v is not None and str(v) != "NULL"),
            key=_natural_key,
        )
        if len(values) > MAX_CATEGORIES:
            warnings.append(
                f"{spec.title}: {len(values)} categorías en {field!r}; se muestran las primeras {MAX_CATEGORIES}."
            )
            values = values[:MAX_CATEGORIES]
        categories = [
            QgsRendererCategory(value, make_symbol(spec, geom, color), str(value))
            for value, color in zip(values, palette_colors(spec.palette, len(values)))
        ]
        layer.setRenderer(QgsCategorizedSymbolRenderer(field, categories))
        info["classes"] = len(categories)
    elif style == "graduated":
        renderer = QgsGraduatedSymbolRenderer(field)
        renderer.setSourceSymbol(make_symbol(spec, geom))
        start, end = (spec.palette + (spec.color, spec.color))[:2]
        renderer.setSourceColorRamp(QgsGradientColorRamp(QColor(start), QColor(end)))
        renderer.setClassificationMethod(QgsClassificationJenks())
        renderer.updateClasses(layer, 5)
        layer.setRenderer(renderer)
        info["classes"] = len(renderer.ranges())
    else:
        layer.setRenderer(QgsSingleSymbolRenderer(make_symbol(spec, geom)))
    layer.triggerRepaint()
    return info


def style_project_area(layer: QgsVectorLayer) -> None:
    symbol = QgsFillSymbol.createSimple(
        {
            "style": "no",
            "outline_color": PROJECT_AREA_COLOR,
            "outline_width": "0.8",
            "outline_style": "solid",
        }
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))


def apply_labels(layer: QgsVectorLayer, spec: LayerType, label_field: str | None = None) -> str | None:
    """Label features with ``label_field`` or the first matching catalog field."""
    available = [f.name() for f in layer.fields()]
    if label_field is not None and label_field not in available:
        raise ValueError(f"El campo de etiqueta {label_field!r} no existe en {layer.name()}.")
    field = label_field or pick_field(spec.label_candidates, available)
    if not field:
        return None

    text = QgsTextFormat()
    font = QFont("Arial")
    font.setItalic(spec.geometry == "line" or spec.key in ("cuerpos_agua",))
    text.setFont(font)
    text.setSize(7 if spec.geometry != "point" else 7.5)
    text.setColor(QColor("#08306b") if spec.key in ("rios", "cuerpos_agua") else QColor("#202020"))
    buffer = QgsTextBufferSettings()
    buffer.setEnabled(True)
    buffer.setSize(0.8)
    buffer.setColor(QColor("white"))
    text.setBuffer(buffer)

    settings = QgsPalLayerSettings()
    settings.fieldName = field
    settings.setFormat(text)
    geom = layer.geometryType()
    if geom == QgsWkbTypes.LineGeometry:
        settings.placement = QgsPalLayerSettings.Curved
    elif geom == QgsWkbTypes.PointGeometry:
        settings.placement = QgsPalLayerSettings.OrderedPositionsAroundPoint
        settings.dist = 1.0
    else:
        settings.placement = QgsPalLayerSettings.Horizontal
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)
    return field


def style_raster(layer: QgsRasterLayer, spec: LayerType) -> dict:
    """Pseudocolor rendering of band 1 using the layer type's palette."""
    provider = layer.dataProvider()
    stats = provider.bandStatistics(1, QgsRasterBandStats.Min | QgsRasterBandStats.Max)
    low, high = stats.minimumValue, stats.maximumValue
    colors = [QColor(c) for c in (spec.palette or (spec.color,))]
    ramp = QgsGradientColorRamp(colors[0], colors[-1])
    steps = 5
    items = []
    previous = low
    for i in range(1, steps + 1):
        upper = low + (high - low) * i / steps
        if len(colors) > 2:
            color = colors[(i - 1) * (len(colors) - 1) // (steps - 1)]
        else:
            color = ramp.color((i - 1) / (steps - 1))
        items.append(QgsColorRampShader.ColorRampItem(upper, color, f"{previous:,.0f} – {upper:,.0f}"))
        previous = upper
    ramp_shader = QgsColorRampShader(low, high)
    ramp_shader.setColorRampType(QgsColorRampShader.Discrete)
    ramp_shader.setColorRampItemList(items)
    shader = QgsRasterShader()
    shader.setRasterShaderFunction(ramp_shader)
    renderer = QgsSingleBandPseudoColorRenderer(provider, 1, shader)
    renderer.setOpacity(spec.opacity)
    layer.setRenderer(renderer)
    layer.triggerRepaint()
    return {"style": "pseudocolor", "field": None, "classes": steps, "range": [low, high], "warnings": []}
