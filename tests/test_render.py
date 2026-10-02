import pytest

pytestmark = pytest.mark.qgis


@pytest.fixture()
def session(sample):
    from qgis_mcp.session import MapSession

    paths = dict(sample)
    s = MapSession()
    s.set_area(paths.pop("area"), "Proyecto Demo")
    for key, path in paths.items():
        s.add_layer(key, path)
    return s


def test_inspect_reports_fields_and_samples(sample):
    from qgis_mcp.data import inspect

    info = inspect(sample["zonas_vida"])
    assert info["kind"] == "vector"
    assert info["geometry"] == "polygon"
    field = next(f for f in info["fields"] if f["name"] == "ZONA_VIDA")
    assert "bh-MB" in field["sample_values"]

    raster = inspect(sample["precipitacion_media"])
    assert raster["kind"] == "raster" and raster["bands"][0]["max"] > raster["bands"][0]["min"]


def test_clip_to_shape_keeps_only_features_inside(sample, qgis_app):
    from qgis.core import QgsCoordinateReferenceSystem

    from qgis_mcp.data import area_geometry, clip_vector, load_vector

    target = QgsCoordinateReferenceSystem("EPSG:32615")
    mask = area_geometry(load_vector(sample["area"]), target)
    clipped = clip_vector(load_vector(sample["comunidades"]), target, mask)
    names = sorted(f["COMUNIDAD"] for f in clipped.getFeatures())
    assert names == ["Aldea El Rosario", "Caserío Las Flores"]

    zones = clip_vector(load_vector(sample["zonas_vida"]), target, mask)
    total = sum(f.geometry().area() for f in zones.getFeatures())
    assert total == pytest.approx(mask.area(), rel=1e-6)


def test_reprojects_layers_in_another_crs(sample, qgis_app):
    from qgis.core import QgsCoordinateReferenceSystem

    from qgis_mcp.data import clip_vector, load_vector

    target = QgsCoordinateReferenceSystem("EPSG:32615")
    municipios = clip_vector(load_vector(sample["ubicacion"]), target, None)
    assert municipios.crs().authid() == "EPSG:32615"
    assert municipios.extent().xMinimum() > 700_000


def test_render_map_with_every_layer(session, tmp_path):
    from qgis_mcp.renderer import render_map

    result = render_map(session, str(tmp_path / "general.pdf"), dpi=72, sources="Datos de prueba")
    assert (tmp_path / "general.pdf").stat().st_size > 10_000
    assert (tmp_path / "general.qgz").exists()
    assert (tmp_path / "general_datos" / "capas.gpkg").exists()
    by_key = {layer["layer_type"]: layer for layer in result["layers"]}
    assert set(by_key) == set(session.layers)
    assert by_key["zonas_vida"]["style"] == "categorized"
    assert by_key["zonas_vida"]["field"] == "ZONA_VIDA"
    assert by_key["indice_humedad"]["style"] == "graduated"
    assert by_key["precipitacion_media"]["style"] == "pseudocolor"
    assert by_key["volcanes"]["clip"] == "none"
    assert by_key["comunidades"]["features"] == 2
    assert by_key["rios"]["label_field"] == "NOMBRE"


def test_render_png_subset_and_custom_crs(session, tmp_path):
    from qgis_mcp.renderer import render_map

    session.crs = "EPSG:4326"
    result = render_map(
        session, str(tmp_path / "rios.png"), layer_types=["rios", "vias_acceso"],
        dpi=60, grid=False, save_project=False,
    )
    session.crs = None
    assert result["crs"] == "EPSG:4326"
    assert result["project"] is None
    assert [layer["layer_type"] for layer in result["layers"]] == ["rios", "vias_acceso"]
    assert (tmp_path / "rios.png").read_bytes()[:4] == b"\x89PNG"


def test_explicit_field_must_exist(session, tmp_path):
    from qgis_mcp.renderer import validate_layer

    session.add_layer("uso_suelo", session.layers["uso_suelo"].path, field="NO_EXISTE")
    with pytest.raises(ValueError, match="NO_EXISTE"):
        validate_layer(session.layers["uso_suelo"])


def test_map_series_one_sheet_per_layer(session, tmp_path):
    from qgis_mcp.renderer import render_series

    result = render_series(
        session, str(tmp_path / "serie"), fmt="png",
        layer_types=["ubicacion", "zonas_vida", "volcanes"], context_layers=["rios"], dpi=50,
    )
    outputs = sorted(p.name for p in (tmp_path / "serie").glob("*.png"))
    assert outputs == ["01_ubicacion.png", "02_zonas_vida.png", "03_volcanes.png"]
    ubicacion, zonas, volcanes = result["maps"]
    # The location sheet zooms out to the whole location layer.
    assert ubicacion["extent"][2] - ubicacion["extent"][0] > 30_000
    assert [layer["layer_type"] for layer in zonas["layers"]] == ["zonas_vida", "rios"]
    # Volcanoes keep a wide regional margin around the project.
    assert volcanes["extent"][2] - volcanes["extent"][0] > zonas["extent"][2] - zonas["extent"][0]
