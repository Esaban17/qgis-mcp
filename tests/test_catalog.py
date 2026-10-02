import pytest

from qgis_mcp.catalog import LAYER_TYPES, get_layer_type, pick_field
from qgis_mcp.session import MapSession, detect_kind

REQUIRED = {
    "ubicacion", "rios", "zonas_vida", "vias_acceso", "cuencas", "cuerpos_agua",
    "areas_protegidas", "temperatura_thornthwaite", "precipitacion_media",
    "humedad_thornthwaite", "indice_humedad", "taxonomia_suelos", "uso_suelo",
    "comunidades", "volcanes",
}


def test_catalog_covers_the_15_project_layers():
    assert {lt.key for lt in LAYER_TYPES} == REQUIRED
    assert len({lt.z for lt in LAYER_TYPES}) > 1


@pytest.mark.parametrize(
    "name,key",
    [("Zonas de Vida", "zonas_vida"), ("VOLCANES", "volcanes"), ("vías", "vias_acceso"), ("holdridge", "zonas_vida")],
)
def test_lookup_by_title_alias_and_accents(name, key):
    assert get_layer_type(name).key == key


def test_unknown_layer_type_lists_valid_keys():
    with pytest.raises(KeyError, match="zonas_vida"):
        get_layer_type("geologia")


def test_pick_field_is_case_insensitive_and_ordered():
    assert pick_field(("ZONA_VIDA", "NOMBRE"), ["id", "nombre", "Zona_Vida"]) == "Zona_Vida"
    assert pick_field(("X",), ["id"]) is None


def test_detect_kind():
    assert detect_kind("a/b.SHP") == "vector"
    assert detect_kind("lluvia.tif") == "raster"
    with pytest.raises(ValueError):
        detect_kind("notas.docx")


def test_session_orders_layers_and_uses_catalog_defaults(tmp_path):
    for name in ("area.shp", "rios.shp", "volcanes.shp", "zv.gpkg"):
        (tmp_path / name).write_bytes(b"")
    session = MapSession()
    session.set_area(str(tmp_path / "area.shp"), "Proyecto X")
    session.add_layer("volcanes", str(tmp_path / "volcanes.shp"))
    session.add_layer("Ríos", str(tmp_path / "rios.shp"), clip="extent")
    session.add_layer("zonas de vida", str(tmp_path / "zv.gpkg"))

    ordered = [e.layer_type for e in session.select(None)]
    assert ordered == ["zonas_vida", "rios", "volcanes"]
    assert session.layers["volcanes"].clip == "none"
    assert session.layers["rios"].clip == "extent"

    session.remove_layer("rios")
    assert "rios" not in session.to_dict()["layers"]
    with pytest.raises(KeyError):
        session.select(["rios"])


def test_session_validates_inputs(tmp_path):
    session = MapSession()
    with pytest.raises(RuntimeError):
        session.require_area()
    with pytest.raises(FileNotFoundError):
        session.add_layer("rios", str(tmp_path / "missing.shp"))
    (tmp_path / "lluvia.tif").write_bytes(b"")
    with pytest.raises(ValueError):
        session.set_area(str(tmp_path / "lluvia.tif"))
    with pytest.raises(ValueError):
        session.add_layer("precipitacion_media", str(tmp_path / "lluvia.tif"), clip="circle")
