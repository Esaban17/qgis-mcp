"""Print layout: map frame, title, legend, north arrow, scale bar and notes."""

from __future__ import annotations

import math
from datetime import date
from pathlib import Path

from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsLayoutExporter,
    QgsLayoutItemLabel,
    QgsLayoutItemLegend,
    QgsLayoutItemMap,
    QgsLayoutItemMapGrid,
    QgsLayoutItemPicture,
    QgsLayoutItemScaleBar,
    QgsLayoutMeasurement,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsLegendStyle,
    QgsPrintLayout,
    QgsProject,
    QgsRectangle,
    QgsTextFormat,
    QgsUnitTypes,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor, QFont

PAGE_SIZES_MM = {
    "A4": (297.0, 210.0),
    "A3": (420.0, 297.0),
    "A2": (594.0, 420.0),
    "LETTER": (279.4, 215.9),
    "LEGAL": (355.6, 215.9),
    "TABLOID": (431.8, 279.4),
}

MARGIN = 10.0
PANEL_WIDTH = 72.0
PANEL_GAP = 6.0
TITLE_HEIGHT = 14.0


def page_size(name: str, orientation: str) -> tuple[float, float]:
    try:
        long_side, short_side = PAGE_SIZES_MM[name.upper()]
    except KeyError:
        raise ValueError(f"Tamaño de página no soportado: {name}. Usa: {', '.join(PAGE_SIZES_MM)}") from None
    if orientation not in ("landscape", "portrait"):
        raise ValueError("orientation debe ser 'landscape' o 'portrait'.")
    return (long_side, short_side) if orientation == "landscape" else (short_side, long_side)


def _text(size: float, bold: bool = False) -> QgsTextFormat:
    fmt = QgsTextFormat()
    font = QFont("Arial")
    font.setBold(bold)
    fmt.setFont(font)
    fmt.setSize(size)
    fmt.setColor(QColor("#202020"))
    return fmt


def _label(layout, text: str, x: float, y: float, w: float, h: float, size: float, bold=False, align=Qt.AlignLeft):
    item = QgsLayoutItemLabel(layout)
    item.setText(text)
    item.setTextFormat(_text(size, bold))
    item.setHAlign(align)
    item.setVAlign(Qt.AlignVCenter if h <= TITLE_HEIGHT else Qt.AlignTop)
    layout.addLayoutItem(item)
    item.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    item.attemptResize(QgsLayoutSize(w, h, QgsUnitTypes.LayoutMillimeters))
    return item


def _nice_interval(span: float, target_lines: int = 4) -> float:
    raw = span / target_lines
    exponent = math.floor(math.log10(raw)) if raw > 0 else 0
    base = raw / 10**exponent
    for step in (1, 2, 2.5, 5, 10):
        if base <= step:
            return step * 10**exponent
    return 10 ** (exponent + 1)


def _north_arrow_svg() -> str | None:
    for root in QgsApplication.svgPaths():
        for name in ("NorthArrow_02.svg", "NorthArrow_01.svg"):
            candidate = Path(root) / "arrows" / name
            if candidate.exists():
                return str(candidate)
    return None


def build_layout(
    project: QgsProject,
    layers: list,
    legend_layers: list,
    extent: QgsRectangle,
    crs: QgsCoordinateReferenceSystem,
    title: str,
    subtitle: str | None,
    notes: list[str],
    page: str = "A4",
    orientation: str = "landscape",
    grid: bool = True,
) -> QgsPrintLayout:
    """Compose the map sheet. ``layers`` are ordered top to bottom."""
    width, height = page_size(page, orientation)
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName(title)
    layout.pageCollection().page(0).setPageSize(QgsLayoutSize(width, height, QgsUnitTypes.LayoutMillimeters))

    _label(layout, title, MARGIN, MARGIN * 0.6, width - 2 * MARGIN, TITLE_HEIGHT * 0.7, 16, bold=True, align=Qt.AlignHCenter)
    if subtitle:
        _label(layout, subtitle, MARGIN, MARGIN * 0.6 + TITLE_HEIGHT * 0.65, width - 2 * MARGIN, 6, 9, align=Qt.AlignHCenter)

    top = MARGIN + TITLE_HEIGHT
    map_w = width - 2 * MARGIN - PANEL_WIDTH - PANEL_GAP
    map_h = height - top - MARGIN
    map_item = QgsLayoutItemMap(layout)
    map_item.setFrameEnabled(True)
    map_item.setFrameStrokeWidth(QgsLayoutMeasurement(0.4))
    layout.addLayoutItem(map_item)
    map_item.attemptMove(QgsLayoutPoint(MARGIN, top, QgsUnitTypes.LayoutMillimeters))
    map_item.attemptResize(QgsLayoutSize(map_w, map_h, QgsUnitTypes.LayoutMillimeters))
    map_item.setCrs(crs)
    map_item.setLayers(layers)
    map_item.setKeepLayerSet(True)
    map_item.zoomToExtent(extent)

    if grid:
        visible = map_item.extent()
        interval = _nice_interval(min(visible.width(), visible.height()))
        map_grid = QgsLayoutItemMapGrid("Coordenadas", map_item)
        map_grid.setStyle(QgsLayoutItemMapGrid.Cross)
        map_grid.setCrossLength(2)
        map_grid.setIntervalX(interval)
        map_grid.setIntervalY(interval)
        map_grid.setAnnotationEnabled(True)
        map_grid.setAnnotationPrecision(4 if crs.isGeographic() else 0)
        map_grid.setAnnotationTextFormat(_text(6))
        map_grid.setAnnotationDirection(QgsLayoutItemMapGrid.Vertical, QgsLayoutItemMapGrid.Left)
        # The right side faces the legend panel; keep it free of labels.
        map_grid.setAnnotationDisplay(QgsLayoutItemMapGrid.HideAll, QgsLayoutItemMapGrid.Right)
        map_grid.setFrameStyle(QgsLayoutItemMapGrid.Zebra)
        map_grid.setFrameWidth(1.2)
        map_item.grids().addGrid(map_grid)

    panel_x = MARGIN + map_w + PANEL_GAP
    y = top

    arrow_svg = _north_arrow_svg()
    if arrow_svg:
        arrow = QgsLayoutItemPicture(layout)
        arrow.setPicturePath(arrow_svg)
        arrow.setLinkedMap(map_item)
        arrow.setNorthMode(QgsLayoutItemPicture.GridNorth)
        layout.addLayoutItem(arrow)
        arrow.attemptMove(QgsLayoutPoint(panel_x + PANEL_WIDTH / 2 - 7, y, QgsUnitTypes.LayoutMillimeters))
        arrow.attemptResize(QgsLayoutSize(14, 18, QgsUnitTypes.LayoutMillimeters))
    else:
        _label(layout, "N\n▲", panel_x, y, PANEL_WIDTH, 18, 14, bold=True, align=Qt.AlignHCenter)
    y += 21

    scalebar = QgsLayoutItemScaleBar(layout)
    scalebar.setStyle("Single Box")
    scalebar.setLinkedMap(map_item)
    scalebar.setUnits(QgsUnitTypes.DistanceKilometers)
    scalebar.setUnitLabel("km")
    scalebar.setNumberOfSegments(3)
    scalebar.setNumberOfSegmentsLeft(0)
    scalebar.setTextFormat(_text(7))
    layout.addLayoutItem(scalebar)
    scalebar.applyDefaultSize(QgsUnitTypes.DistanceKilometers)
    scalebar.setMaximumBarWidth(PANEL_WIDTH - 8)
    scalebar.update()
    scalebar.attemptMove(QgsLayoutPoint(panel_x + 2, y, QgsUnitTypes.LayoutMillimeters))
    y += 12

    scale_text = f"Escala aproximada 1:{_round_scale(map_item.scale()):,}".replace(",", " ")
    _label(layout, scale_text, panel_x, y, PANEL_WIDTH, 5, 7, align=Qt.AlignHCenter)
    y += 7

    notes_height = 6 + 4 * len(notes)
    legend = QgsLayoutItemLegend(layout)
    legend.setTitle("Leyenda")
    legend.setLinkedMap(map_item)
    legend.setAutoUpdateModel(False)
    root = legend.model().rootGroup()
    root.removeAllChildren()
    for layer in legend_layers:
        root.addLayer(layer)
    legend.setLegendFilterByMapEnabled(True)
    legend.setSymbolHeight(3.5)
    legend.setSymbolWidth(6)
    legend.setWrapString("|")
    for style, size, bold in (
        (QgsLegendStyle.Title, 10, True),
        (QgsLegendStyle.Group, 8, True),
        (QgsLegendStyle.Subgroup, 7.5, True),
        (QgsLegendStyle.SymbolLabel, 6.5, False),
    ):
        legend.rstyle(style).setTextFormat(_text(size, bold))
    legend.setFrameEnabled(False)
    legend.setResizeToContents(False)
    layout.addLayoutItem(legend)
    legend.attemptMove(QgsLayoutPoint(panel_x, y, QgsUnitTypes.LayoutMillimeters))
    legend_height = max(20.0, height - MARGIN - y - notes_height - 2)
    legend.attemptResize(QgsLayoutSize(PANEL_WIDTH, legend_height, QgsUnitTypes.LayoutMillimeters))
    legend.refresh()

    note_text = "\n".join(notes)
    _label(layout, note_text, panel_x, height - MARGIN - notes_height, PANEL_WIDTH, notes_height, 6)
    return layout


def _round_scale(scale: float) -> int:
    if scale <= 0:
        return 0
    magnitude = 10 ** max(0, int(math.log10(scale)) - 1)
    return int(round(scale / magnitude) * magnitude)


def default_notes(project_name: str, crs: QgsCoordinateReferenceSystem, sources: str | None) -> list[str]:
    notes = [
        f"Proyecto: {project_name}",
        f"Sistema de referencia: {crs.authid()} {crs.description()}".strip(),
    ]
    if sources:
        notes.append(f"Fuentes: {sources}")
    notes.append(f"Fecha: {date.today():%d/%m/%Y}")
    return notes


def export(layout: QgsPrintLayout, output_path: str, dpi: int = 300) -> str:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    exporter = QgsLayoutExporter(layout)
    suffix = out.suffix.lower()
    if suffix == ".pdf":
        settings = QgsLayoutExporter.PdfExportSettings()
        settings.dpi = dpi
        settings.rasterizeWholeImage = False
        result = exporter.exportToPdf(str(out), settings)
    elif suffix in (".png", ".jpg", ".jpeg", ".tif", ".tiff"):
        settings = QgsLayoutExporter.ImageExportSettings()
        settings.dpi = dpi
        result = exporter.exportToImage(str(out), settings)
    else:
        raise ValueError("La salida debe terminar en .pdf, .png, .jpg o .tif")
    if result != QgsLayoutExporter.Success:
        raise RuntimeError(f"QGIS no pudo exportar el mapa (código {result}): {exporter.errorMessage()}")
    return str(out.resolve())
