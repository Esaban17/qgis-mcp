"""MCP server that builds thematic maps with QGIS.

The package doubles as a QGIS plugin: copy it into the QGIS plugins folder
(``qgis-mcp-install-plugin`` does it) and QGIS calls ``classFactory``.
"""

__version__ = "0.1.0"


def classFactory(iface):  # noqa: N802 (name required by QGIS)
    from .plugin import QgisMcpPlugin

    return QgisMcpPlugin(iface)
