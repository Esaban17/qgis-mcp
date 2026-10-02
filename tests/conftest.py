import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

HAS_QGIS = importlib.util.find_spec("qgis") is not None


def pytest_collection_modifyitems(config, items):
    if HAS_QGIS:
        return
    skip = pytest.mark.skip(reason="PyQGIS no está disponible en este entorno")
    for item in items:
        if "qgis" in item.keywords:
            item.add_marker(skip)


def pytest_configure(config):
    config.addinivalue_line("markers", "qgis: requires PyQGIS")


@pytest.fixture(scope="session")
def qgis_app():
    from qgis_mcp.qgis_env import ensure_qgis

    return ensure_qgis()


@pytest.fixture(scope="session")
def sample(qgis_app, tmp_path_factory):
    import sample_data

    return sample_data.build(tmp_path_factory.mktemp("datos"))
