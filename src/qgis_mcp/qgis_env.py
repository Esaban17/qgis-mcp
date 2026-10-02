"""Start (or reuse) a headless QGIS application."""

from __future__ import annotations

import os

_app = None


def ensure_qgis():
    """Initialise QGIS once per process and return the QgsApplication.

    Inside a running QGIS (e.g. the Python console) the existing instance is
    reused. Otherwise QGIS starts without a display; set ``QGIS_PREFIX_PATH``
    when QGIS is not installed in a standard location (Windows, macOS).
    """
    global _app
    if _app is not None:
        return _app

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qgis.core import QgsApplication

    existing = QgsApplication.instance()
    if existing is not None:
        _app = existing
        return _app

    prefix = os.environ.get("QGIS_PREFIX_PATH")
    if prefix:
        QgsApplication.setPrefixPath(prefix, True)
    _app = QgsApplication([], False)
    _app.initQgis()
    return _app
