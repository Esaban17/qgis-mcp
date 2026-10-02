# qgis-mcp

Servidor [MCP](https://modelcontextprotocol.io) para generar mapas temáticos en QGIS
desde un asistente (Claude Desktop, Claude Code u otro cliente MCP).

El objetivo es componer mapas de proyecto con capas temáticas (ubicación, ríos, zonas
de vida, vías de acceso, cuencas, cuerpos de agua, áreas protegidas, temperatura y
humedad según Thornthwaite, precipitación media, índice de humedad, taxonomía y uso
de suelos, comunidades y volcanes) dibujadas encima del shape del proyecto.

## Cómo funciona

```
Cliente MCP  ──stdio──▶  servidor qgis-mcp  ──socket 127.0.0.1:9876──▶  plugin dentro de QGIS
```

- `src/qgis_mcp/`: servidor MCP en Python. Cada herramienta envía una orden JSON al plugin.
- `qgis_plugin/qgis_mcp_plugin/`: plugin de QGIS que escucha en el puerto local y ejecuta
  las órdenes con PyQGIS en el hilo principal de QGIS.

## Instalación

### 1. Plugin de QGIS (3.22 o superior)

Copia la carpeta `qgis_plugin/qgis_mcp_plugin` al directorio de plugins de tu perfil:

- Windows: `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`
- macOS: `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/`
- Linux: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`

Reinicia QGIS, activa **QGIS MCP** en *Complementos ▸ Administrar e instalar
complementos* y pulsa el botón **QGIS MCP: iniciar servidor** en la barra de herramientas.

### 2. Servidor MCP

Con [uv](https://docs.astral.sh/uv/):

```json
{
  "mcpServers": {
    "qgis": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/Esaban17/qgis-mcp", "qgis-mcp"]
    }
  }
}
```

Variables opcionales: `QGIS_MCP_HOST`, `QGIS_MCP_PORT` (por defecto `9876`) y
`QGIS_MCP_TIMEOUT` en segundos (por defecto `120`).

## Herramientas

| Herramienta | Qué hace |
|---|---|
| `ping` | Comprueba que QGIS y el plugin responden |
| `get_project_info` | CRS, archivo del proyecto y capas cargadas |
| `load_project_shape` | Carga el shape del proyecto como base (contorno rojo, sin relleno) y encuadra el mapa |
| `add_layer` | Agrega una capa vectorial o ráster encima, con estilo `.qml` opcional |
| `list_layers` | Capas en orden de dibujo |
| `remove_layer` | Quita una capa por id o nombre |
| `zoom_to_project` | Encuadra el mapa en el shape del proyecto |
| `export_map` | Exporta a PDF/PNG/JPG un layout A4 con título, leyenda y escala |
| `save_project` | Guarda el proyecto `.qgz` |

## Desarrollo

```bash
uv venv && uv pip install -e '.[dev]'
.venv/bin/python -m pytest
```

Las pruebas cubren el protocolo entre el servidor y el plugin con un socket simulado;
el plugin se prueba dentro de QGIS.
