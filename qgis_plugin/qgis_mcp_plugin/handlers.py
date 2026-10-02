"""Órdenes que el servidor MCP puede ejecutar dentro de QGIS."""

import os

from qgis.PyQt.QtGui import QColor, QFont
from qgis.core import (
    QgsCoordinateTransform,
    QgsLayoutExporter,
    QgsLayoutItemLabel,
    QgsLayoutItemLegend,
    QgsLayoutItemMap,
    QgsLayoutItemScaleBar,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsPrintLayout,
    QgsProject,
    QgsRasterLayer,
    QgsUnitTypes,
    QgsVectorLayer,
)

RASTER_EXTENSIONS = {".tif", ".tiff", ".img", ".asc", ".vrt", ".jp2", ".ecw"}
PROJECT_SHAPE_KEY = ("qgis_mcp", "project_shape_id")


class CommandHandlers:
    def __init__(self, iface):
        self.iface = iface
        self._commands = {
            "ping": self.ping,
            "get_project_info": self.get_project_info,
            "load_project_shape": self.load_project_shape,
            "add_layer": self.add_layer,
            "list_layers": self.list_layers,
            "remove_layer": self.remove_layer,
            "zoom_to_project": self.zoom_to_project,
            "export_map": self.export_map,
            "save_project": self.save_project,
        }

    def get(self, command):
        return self._commands.get(command)

    # --- Órdenes -----------------------------------------------------------

    def ping(self):
        return "pong"

    def get_project_info(self):
        project = QgsProject.instance()
        shape = self._project_shape()
        return {
            "file": project.fileName() or None,
            "crs": project.crs().authid(),
            "project_shape": shape.name() if shape else None,
            "layers": self.list_layers(),
        }

    def load_project_shape(self, path, name="Área del proyecto"):
        layer = QgsVectorLayer(path, name, "ogr")
        if not layer.isValid():
            raise ValueError(f"No se pudo abrir el shape del proyecto: {path}")

        symbol = layer.renderer().symbol() if layer.renderer() else None
        if symbol is not None:
            symbol.setColor(QColor(255, 255, 255, 0))
            symbol_layer = symbol.symbolLayer(0)
            if hasattr(symbol_layer, "setStrokeColor"):
                symbol_layer.setStrokeColor(QColor(200, 0, 0))
                symbol_layer.setStrokeWidth(0.8)

        project = QgsProject.instance()
        previous = self._project_shape()
        if previous is not None:
            project.removeMapLayer(previous.id())

        # El shape del proyecto va al fondo: las capas temáticas se dibujan encima.
        project.addMapLayer(layer, False)
        project.layerTreeRoot().addLayer(layer)
        project.writeEntry(*PROJECT_SHAPE_KEY, layer.id())
        if not project.crs().isValid():
            project.setCrs(layer.crs())

        self.zoom_to_project()
        return self._describe(layer)

    def add_layer(self, path, name=None, style_path=None):
        name = name or os.path.splitext(os.path.basename(path))[0]
        if os.path.splitext(path)[1].lower() in RASTER_EXTENSIONS:
            layer = QgsRasterLayer(path, name)
        else:
            layer = QgsVectorLayer(path, name, "ogr")
        if not layer.isValid():
            raise ValueError(f"No se pudo abrir la capa: {path}")

        if style_path:
            message, ok = layer.loadNamedStyle(style_path)
            if not ok:
                raise ValueError(f"No se pudo aplicar el estilo {style_path}: {message}")

        project = QgsProject.instance()
        project.addMapLayer(layer, False)
        project.layerTreeRoot().insertLayer(0, layer)
        return self._describe(layer)

    def list_layers(self):
        root = QgsProject.instance().layerTreeRoot()
        return [self._describe(node.layer()) for node in root.findLayers() if node.layer()]

    def remove_layer(self, layer):
        target = self._find_layer(layer)
        name = target.name()
        QgsProject.instance().removeMapLayer(target.id())
        return {"removed": name}

    def zoom_to_project(self, margin_percent=10.0):
        extent = self._project_extent(margin_percent)
        canvas = self.iface.mapCanvas()
        canvas.setExtent(extent)
        canvas.refresh()
        return {"extent": extent.toString()}

    def export_map(self, output_path, title="", dpi=300, margin_percent=10.0):
        project = QgsProject.instance()
        layout = QgsPrintLayout(project)
        layout.initializeDefaults()  # A4 horizontal
        layout.setName("QGIS MCP")

        map_item = QgsLayoutItemMap(layout)
        map_item.attemptMove(QgsLayoutPoint(10, 20, QgsUnitTypes.LayoutMillimeters))
        map_item.attemptResize(QgsLayoutSize(200, 180, QgsUnitTypes.LayoutMillimeters))
        map_item.setFrameEnabled(True)
        map_item.zoomToExtent(self._project_extent(margin_percent))
        layout.addLayoutItem(map_item)

        if title:
            label = QgsLayoutItemLabel(layout)
            label.setText(title)
            label.setFont(QFont("Arial", 18, QFont.Bold))
            label.attemptMove(QgsLayoutPoint(10, 5, QgsUnitTypes.LayoutMillimeters))
            label.attemptResize(QgsLayoutSize(277, 12, QgsUnitTypes.LayoutMillimeters))
            layout.addLayoutItem(label)

        legend = QgsLayoutItemLegend(layout)
        legend.setTitle("Leyenda")
        legend.setLinkedMap(map_item)
        legend.attemptMove(QgsLayoutPoint(215, 20, QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(legend)

        scale_bar = QgsLayoutItemScaleBar(layout)
        scale_bar.setStyle("Single Box")
        scale_bar.setLinkedMap(map_item)
        scale_bar.applyDefaultSize()
        scale_bar.attemptMove(QgsLayoutPoint(215, 185, QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(scale_bar)

        exporter = QgsLayoutExporter(layout)
        extension = os.path.splitext(output_path)[1].lower()
        if extension == ".pdf":
            settings = QgsLayoutExporter.PdfExportSettings()
            settings.dpi = dpi
            result = exporter.exportToPdf(output_path, settings)
        elif extension in {".png", ".jpg", ".jpeg"}:
            settings = QgsLayoutExporter.ImageExportSettings()
            settings.dpi = dpi
            result = exporter.exportToImage(output_path, settings)
        else:
            raise ValueError("output_path debe terminar en .pdf, .png o .jpg")

        if result != QgsLayoutExporter.Success:
            raise RuntimeError(f"La exportación falló (código {result})")
        return {"output_path": output_path}

    def save_project(self, path=None):
        project = QgsProject.instance()
        ok = project.write(path) if path else project.write()
        if not ok:
            raise RuntimeError("No se pudo guardar el proyecto")
        return {"file": project.fileName()}

    # --- Utilidades --------------------------------------------------------

    def _project_shape(self):
        layer_id, found = QgsProject.instance().readEntry(*PROJECT_SHAPE_KEY)
        if not found or not layer_id:
            return None
        return QgsProject.instance().mapLayer(layer_id)

    def _project_extent(self, margin_percent):
        shape = self._project_shape()
        if shape is None:
            raise ValueError("Primero carga el shape del proyecto con load_project_shape")
        project = QgsProject.instance()
        extent = shape.extent()
        if shape.crs() != project.crs():
            transform = QgsCoordinateTransform(shape.crs(), project.crs(), project)
            extent = transform.transformBoundingBox(extent)
        extent.scale(1 + margin_percent / 100.0)
        return extent

    def _find_layer(self, layer):
        project = QgsProject.instance()
        target = project.mapLayer(layer)
        if target is None:
            matches = project.mapLayersByName(layer)
            target = matches[0] if matches else None
        if target is None:
            raise ValueError(f"No existe la capa: {layer}")
        return target

    def _describe(self, layer):
        return {
            "id": layer.id(),
            "name": layer.name(),
            "type": "raster" if isinstance(layer, QgsRasterLayer) else "vector",
            "crs": layer.crs().authid(),
            "source": layer.source(),
        }
