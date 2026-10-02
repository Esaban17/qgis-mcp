def classFactory(iface):
    from .plugin import QgisMcpPlugin

    return QgisMcpPlugin(iface)
