"""Synthetic datasets for the 15 layer types around a fake project in Guatemala.

Coordinates are WGS 84 / UTM 15N (EPSG:32615) except the location layer,
which is in EPSG:4326 to exercise reprojection.
"""

from __future__ import annotations

from pathlib import Path

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant

X0, Y0 = 750_000.0, 1_620_000.0  # project origin (UTM 15N)
SIZE = 4_000.0
UTM = "EPSG:32615"


def _rect(x, y, w, h) -> QgsGeometry:
    return QgsGeometry.fromWkt(f"POLYGON(({x} {y},{x + w} {y},{x + w} {y + h},{x} {y + h},{x} {y}))")


def _write(path: Path, geom_type: str, crs: str, fields: list[tuple[str, QVariant]], rows: list[tuple[QgsGeometry, list]]) -> str:
    layer = QgsVectorLayer(f"{geom_type}?crs={crs}", path.stem, "memory")
    layer.dataProvider().addAttributes([QgsField(name, kind) for name, kind in fields])
    layer.updateFields()
    features = []
    for geom, attrs in rows:
        feat = QgsFeature(layer.fields())
        feat.setGeometry(geom)
        feat.setAttributes(attrs)
        features.append(feat)
    layer.dataProvider().addFeatures(features)
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = {".shp": "ESRI Shapefile", ".gpkg": "GPKG", ".geojson": "GeoJSON"}[path.suffix]
    options.fileEncoding = "UTF-8"
    error, message, *_ = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, str(path), QgsProject.instance().transformContext(), options
    )
    assert error == QgsVectorFileWriter.NoError, message
    return str(path)


def _bands(field: str, labels: list[str], kind=QVariant.String) -> tuple[list, list]:
    """Vertical strips covering the project and its surroundings."""
    n = len(labels)
    width = SIZE * 3 / n
    rows = [(_rect(X0 - SIZE + i * width, Y0 - SIZE, width, SIZE * 3), [label]) for i, label in enumerate(labels)]
    return [(field, kind)], rows


def _raster(path: Path) -> str:
    from osgeo import gdal, osr

    import numpy as np

    cols = rows = 60
    pixel = SIZE * 3 / cols
    ds = gdal.GetDriverByName("GTiff").Create(str(path), cols, rows, 1, gdal.GDT_Float32)
    ds.SetGeoTransform((X0 - SIZE, pixel, 0, Y0 + 2 * SIZE, 0, -pixel))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(32615)
    ds.SetProjection(srs.ExportToWkt())
    xs, ys = np.meshgrid(np.arange(cols), np.arange(rows))
    ds.GetRasterBand(1).WriteArray((1200 + 25 * xs + 10 * ys).astype("float32"))
    ds.GetRasterBand(1).SetNoDataValue(-9999)
    ds.FlushCache()
    ds = None
    return str(path)


def build(directory: str | Path) -> dict[str, str]:
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}

    paths["area"] = _write(
        d / "area_proyecto.shp", "Polygon", UTM, [("CODIGO", QVariant.String)],
        [(QgsGeometry.fromWkt(
            f"POLYGON(({X0} {Y0},{X0 + SIZE} {Y0 + 500},{X0 + SIZE - 300} {Y0 + SIZE},{X0 + 400} {Y0 + SIZE - 200},{X0} {Y0}))"
        ), ["P-01"])],
    )

    to_wgs = QgsCoordinateTransform(
        QgsCoordinateReferenceSystem(UTM), QgsCoordinateReferenceSystem("EPSG:4326"), QgsProject.instance()
    )
    municipios = []
    for i, name in enumerate(["San Juan", "Santa María", "El Progreso", "La Unión"]):
        geom = _rect(X0 - 20_000 + (i % 2) * 22_000, Y0 - 20_000 + (i // 2) * 22_000, 22_000, 22_000)
        geom.transform(to_wgs)
        municipios.append((geom, [name, "Escuintla"]))
    paths["ubicacion"] = _write(
        d / "municipios.geojson", "Polygon", "EPSG:4326",
        [("MUNICIPIO", QVariant.String), ("DEPARTAMEN", QVariant.String)], municipios,
    )

    paths["rios"] = _write(
        d / "rios.shp", "LineString", UTM, [("NOMBRE", QVariant.String)],
        [
            (QgsGeometry.fromPolylineXY([QgsPointXY(X0 - 2000, Y0 + 1500), QgsPointXY(X0 + 2000, Y0 + 1800), QgsPointXY(X0 + 6000, Y0 + 1200)]), ["Río Achiguate"]),
            (QgsGeometry.fromPolylineXY([QgsPointXY(X0 + 1500, Y0 + 6000), QgsPointXY(X0 + 1800, Y0 + 1800)]), ["Quebrada Seca"]),
        ],
    )
    fields, rows = _bands("ZONA_VIDA", ["bh-S(t)", "bmh-S(c)", "bh-MB"])
    paths["zonas_vida"] = _write(d / "zonas_vida.gpkg", "Polygon", UTM, fields, rows)
    paths["vias_acceso"] = _write(
        d / "vias.shp", "LineString", UTM, [("TIPO", QVariant.String), ("RUTA", QVariant.String)],
        [
            (QgsGeometry.fromPolylineXY([QgsPointXY(X0 - 2000, Y0 + 300), QgsPointXY(X0 + 6000, Y0 + 3500)]), ["Asfaltada", "CA-2"]),
            (QgsGeometry.fromPolylineXY([QgsPointXY(X0 + 2500, Y0 - 1000), QgsPointXY(X0 + 2200, Y0 + 3000)]), ["Terracería", "RD-ESC-5"]),
        ],
    )
    fields, rows = _bands("CUENCA", ["Achiguate", "María Linda"])
    paths["cuencas"] = _write(d / "cuencas.shp", "Polygon", UTM, fields, rows)
    paths["cuerpos_agua"] = _write(
        d / "cuerpos_agua.shp", "Polygon", UTM, [("NOMBRE", QVariant.String)],
        [(_rect(X0 + 2600, Y0 + 2400, 600, 400), ["Laguna El Pino"])],
    )
    paths["areas_protegidas"] = _write(
        d / "areas_protegidas.shp", "Polygon", UTM, [("NOMBRE", QVariant.String), ("CATEGORIA", QVariant.String)],
        [(_rect(X0 + 2500, Y0 + 2500, 3000, 3000), ["Reserva Natural Privada", "Reserva Natural Privada"])],
    )
    fields, rows = _bands("TEMPERATUR", ["Megatermal (A')", "Mesotermal (B'4)"])
    paths["temperatura_thornthwaite"] = _write(d / "temperatura.shp", "Polygon", UTM, fields, rows)
    paths["precipitacion_media"] = _raster(d / "precipitacion.tif")
    fields, rows = _bands("HUMEDAD", ["Húmedo (B2)", "Muy húmedo (B3)", "Subhúmedo (C2)"])
    paths["humedad_thornthwaite"] = _write(d / "humedad.shp", "Polygon", UTM, fields, rows)
    fields, rows = _bands("IM", [12.5, 35.0, 61.2, 88.9, 104.3], QVariant.Double)
    paths["indice_humedad"] = _write(d / "indice_humedad.shp", "Polygon", UTM, fields, rows)
    fields, rows = _bands("ORDEN", ["Andisols", "Inceptisols", "Entisols"])
    paths["taxonomia_suelos"] = _write(d / "suelos.shp", "Polygon", UTM, fields, rows)
    fields, rows = _bands("USO", ["Agricultura anual", "Bosque latifoliado", "Pastos", "Café"])
    paths["uso_suelo"] = _write(d / "uso_suelo.shp", "Polygon", UTM, fields, rows)
    paths["comunidades"] = _write(
        d / "comunidades.shp", "Point", UTM, [("COMUNIDAD", QVariant.String)],
        [
            (QgsGeometry.fromPointXY(QgsPointXY(X0 + 1200, Y0 + 1200)), ["Aldea El Rosario"]),
            (QgsGeometry.fromPointXY(QgsPointXY(X0 + 3000, Y0 + 3200)), ["Caserío Las Flores"]),
            (QgsGeometry.fromPointXY(QgsPointXY(X0 + 50_000, Y0)), ["Lejos del proyecto"]),
        ],
    )
    paths["volcanes"] = _write(
        d / "volcanes.shp", "Point", UTM, [("NOMBRE", QVariant.String)],
        [
            (QgsGeometry.fromPointXY(QgsPointXY(X0 - 3000, Y0 + 7000)), ["Volcán de Agua"]),
            (QgsGeometry.fromPointXY(QgsPointXY(X0 + 8000, Y0 + 6500)), ["Volcán de Pacaya"]),
        ],
    )
    return paths
