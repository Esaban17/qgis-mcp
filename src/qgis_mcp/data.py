"""Loading, inspecting and clipping datasets with PyQGIS."""

from __future__ import annotations

from pathlib import Path

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsGeometry,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsWkbTypes,
)

from .session import detect_kind

_GEOMETRY_NAMES = {
    QgsWkbTypes.PointGeometry: "point",
    QgsWkbTypes.LineGeometry: "line",
    QgsWkbTypes.PolygonGeometry: "polygon",
}


def load_vector(path: str, name: str | None = None, subset: str | None = None) -> QgsVectorLayer:
    layer = QgsVectorLayer(path, name or Path(path).stem, "ogr")
    if not layer.isValid():
        raise ValueError(f"No se pudo abrir la capa vectorial: {path}")
    if subset and not layer.setSubsetString(subset):
        raise ValueError(f"Filtro inválido para {path}: {subset}")
    return layer


def load_raster(path: str, name: str | None = None) -> QgsRasterLayer:
    layer = QgsRasterLayer(path, name or Path(path).stem, "gdal")
    if not layer.isValid():
        raise ValueError(f"No se pudo abrir la capa ráster: {path}")
    return layer


def load(path: str, name: str | None = None, subset: str | None = None):
    if detect_kind(path) == "raster":
        return load_raster(path, name)
    return load_vector(path, name, subset)


def geometry_name(layer: QgsVectorLayer) -> str:
    return _GEOMETRY_NAMES.get(layer.geometryType(), "unknown")


def field_names(layer: QgsVectorLayer) -> list[str]:
    return [f.name() for f in layer.fields()]


def inspect(path: str, sample_values: int = 8) -> dict:
    """Describe a dataset so the caller can pick classification/label fields."""
    layer = load(path)
    info: dict = {
        "path": str(Path(path).resolve()),
        "crs": layer.crs().authid() or layer.crs().toWkt()[:80],
        "extent": _rect_to_list(layer.extent()),
    }
    if isinstance(layer, QgsRasterLayer):
        provider = layer.dataProvider()
        bands = []
        for band in range(1, layer.bandCount() + 1):
            stats = provider.bandStatistics(band)
            bands.append({"band": band, "min": stats.minimumValue, "max": stats.maximumValue})
        info.update(kind="raster", width=layer.width(), height=layer.height(), bands=bands)
        return info

    fields = []
    for index, fld in enumerate(layer.fields()):
        entry = {"name": fld.name(), "type": fld.typeName()}
        values = sorted(
            (v for v in layer.uniqueValues(index, sample_values + 1) if v is not None and str(v) != "NULL"),
            key=str,
        )
        entry["sample_values"] = [str(v) for v in values[:sample_values]]
        entry["has_more_values"] = len(values) > sample_values
        fields.append(entry)
    info.update(
        kind="vector",
        geometry=geometry_name(layer),
        feature_count=layer.featureCount(),
        fields=fields,
    )
    return info


def _rect_to_list(rect: QgsRectangle) -> list[float]:
    return [rect.xMinimum(), rect.yMinimum(), rect.xMaximum(), rect.yMaximum()]


def transform_for(source: QgsCoordinateReferenceSystem, target: QgsCoordinateReferenceSystem) -> QgsCoordinateTransform:
    return QgsCoordinateTransform(source, target, QgsProject.instance().transformContext())


def area_geometry(layer: QgsVectorLayer, target: QgsCoordinateReferenceSystem) -> QgsGeometry:
    """Union of every polygon in the project shape, in the target CRS."""
    if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
        raise ValueError("El shape del proyecto debe contener polígonos.")
    xform = transform_for(layer.crs(), target)
    parts = []
    for feature in layer.getFeatures():
        geom = QgsGeometry(feature.geometry())
        if geom.isNull() or geom.isEmpty():
            continue
        geom = geom.makeValid()
        geom.transform(xform)
        parts.append(geom)
    if not parts:
        raise ValueError("El shape del proyecto no tiene geometrías.")
    return QgsGeometry.unaryUnion(parts)


def layer_extent(layer, target: QgsCoordinateReferenceSystem) -> QgsRectangle:
    return transform_for(layer.crs(), target).transformBoundingBox(layer.extent())


def buffered_extent(rect: QgsRectangle, margin_percent: float) -> QgsRectangle:
    size = max(rect.width(), rect.height()) or 1.0
    pad = size * margin_percent / 100.0
    out = QgsRectangle(rect)
    out.grow(pad)
    return out


def clip_vector(
    layer: QgsVectorLayer,
    target: QgsCoordinateReferenceSystem,
    mask: QgsGeometry | None,
) -> QgsVectorLayer:
    """Reproject ``layer`` to ``target`` and cut it with ``mask`` (if any).

    Returns a memory layer with the same attributes.
    """
    geom_type = layer.wkbType()
    out_type = QgsWkbTypes.multiType(geom_type)
    uri = f"{QgsWkbTypes.displayString(out_type)}?crs={target.authid() or 'EPSG:4326'}"
    out = QgsVectorLayer(uri, layer.name(), "memory")
    if not target.authid():
        out.setCrs(target)
    provider = out.dataProvider()
    provider.addAttributes(layer.fields().toList())
    out.updateFields()

    xform = transform_for(layer.crs(), target)
    engine = None
    if mask is not None:
        engine = QgsGeometry.createGeometryEngine(mask.constGet())
        engine.prepareGeometry()
    request_rect = None
    if mask is not None:
        request_rect = transform_for(target, layer.crs()).transformBoundingBox(mask.boundingBox())

    features = []
    iterator = layer.getFeatures(request_rect) if request_rect is not None else layer.getFeatures()
    for feature in iterator:
        geom = QgsGeometry(feature.geometry())
        if geom.isNull() or geom.isEmpty():
            continue
        geom.transform(xform)
        if engine is not None:
            if not engine.intersects(geom.constGet()):
                continue
            if not engine.contains(geom.constGet()):
                if layer.geometryType() == QgsWkbTypes.PolygonGeometry:
                    geom = geom.makeValid()
                geom = geom.intersection(mask)
                if geom.isNull() or geom.isEmpty():
                    continue
                if QgsWkbTypes.geometryType(geom.wkbType()) != layer.geometryType():
                    geom = geom.convertToType(layer.geometryType(), True)
                    if geom is None or geom.isNull() or geom.isEmpty():
                        continue
        if not geom.isMultipart():
            geom.convertToMultiType()
        new = QgsFeature(out.fields())
        new.setAttributes(feature.attributes())
        new.setGeometry(geom)
        features.append(new)
    provider.addFeatures(features)
    out.updateExtents()
    return out


def write_to_geopackage(layer: QgsVectorLayer, gpkg_path: str, table: str) -> QgsVectorLayer:
    """Save a (memory) layer as a table in a GeoPackage and reopen it from disk."""
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = table
    options.fileEncoding = "UTF-8"
    options.actionOnExistingFile = (
        QgsVectorFileWriter.CreateOrOverwriteLayer
        if Path(gpkg_path).exists()
        else QgsVectorFileWriter.CreateOrOverwriteFile
    )
    error, message, *_ = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, gpkg_path, QgsProject.instance().transformContext(), options
    )
    if error != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"No se pudo guardar {table} en {gpkg_path}: {message}")
    saved = QgsVectorLayer(f"{gpkg_path}|layername={table}", layer.name(), "ogr")
    if not saved.isValid():
        raise RuntimeError(f"No se pudo reabrir {table} desde {gpkg_path}")
    return saved


def clip_raster(
    path: str,
    out_path: str,
    target: QgsCoordinateReferenceSystem,
    mask_path: str | None,
    bounds: QgsRectangle | None,
) -> str:
    """Reproject a raster and cut it to a mask file (or to bounds) with GDAL."""
    from osgeo import gdal

    gdal.UseExceptions()
    kwargs = {"dstSRS": target.toWkt(), "dstNodata": -9999, "format": "GTiff"}
    if mask_path:
        kwargs.update(cutlineDSName=mask_path, cropToCutline=True)
    elif bounds is not None:
        kwargs.update(outputBounds=_rect_to_list(bounds), outputBoundsSRS=target.toWkt())
    result = gdal.Warp(out_path, path, **kwargs)
    if result is None:
        raise RuntimeError(f"No se pudo recortar el ráster {path}")
    result = None  # flush to disk
    return out_path


def write_mask(geometry: QgsGeometry, crs: QgsCoordinateReferenceSystem, path: str) -> str:
    """Write a single polygon to GeoJSON (used as a GDAL cutline)."""
    layer = QgsVectorLayer("MultiPolygon", "mask", "memory")
    layer.setCrs(crs)
    feature = QgsFeature()
    feature.setGeometry(geometry)
    layer.dataProvider().addFeatures([feature])
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GeoJSON"
    error, message, *_ = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, path, QgsProject.instance().transformContext(), options
    )
    if error != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"No se pudo escribir la máscara: {message}")
    return path
