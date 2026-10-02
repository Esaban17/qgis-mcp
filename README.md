# qgis-mcp

Servidor [MCP](https://modelcontextprotocol.io) que controla QGIS para generar mapas
temáticos sobre el shape (polígono) de un proyecto. Las capas aparecen en el lienzo de
QGIS a medida que se agregan, y cada mapa queda como diseño de impresión en el
Administrador de diseños, listo para retocar. Además se exporta en PDF/PNG y las capas
recortadas se guardan en un GeoPackage.

```
Cliente MCP  ──stdio──▶  servidor qgis-mcp  ──socket 127.0.0.1:9876──▶  complemento QGIS MCP (dentro de QGIS)
```

El mismo paquete es el servidor y el complemento de QGIS. Si no quieres abrir QGIS,
`QGIS_MCP_MODE=headless` ejecuta todo con PyQGIS sin ventana y guarda un `.qgz` junto
a cada mapa.

## Capas que sabe dibujar

| Clave | Capa | Estilo por defecto | Recorte por defecto |
|---|---|---|---|
| `ubicacion` | Ubicación (país, departamentos, municipios) | un color, etiquetas por municipio | ninguno, el mapa se ajusta a la capa |
| `rios` | Ríos | línea azul, etiqueta curva | al shape |
| `zonas_vida` | Zonas de Vida (Holdridge) | por categoría | al shape |
| `vias_acceso` | Vías de Acceso | por tipo de vía | al shape |
| `cuencas` | Cuencas Hidrográficas | por cuenca | al shape |
| `cuerpos_agua` | Cuerpos de Agua | relleno azul | al shape |
| `areas_protegidas` | Áreas Protegidas | por categoría de manejo | al shape |
| `temperatura_thornthwaite` | Temperatura (Thornthwaite) | por clase | al shape |
| `precipitacion_media` | Precipitación Media Anual | rangos (Jenks) o ráster en 5 clases | al shape |
| `humedad_thornthwaite` | Humedad (Thornthwaite) | por clase | al shape |
| `indice_humedad` | Índice de Humedad | rangos o ráster | al shape |
| `taxonomia_suelos` | Taxonomía de Suelos | por orden | al shape |
| `uso_suelo` | Uso de Suelo | por categoría | al shape |
| `comunidades` | Comunidades | punto negro con nombre | al marco del mapa |
| `volcanes` | Volcanes de la región | triángulo rojo con nombre | ninguno, margen regional amplio |

El campo para clasificar y el de etiquetas se detectan solos (por ejemplo `ZONA_VIDA`,
`CUENCA`, `ORDEN`, `USO`, `NOMBRE`); se pueden indicar con `field` y `label_field`.
El área del proyecto siempre se dibuja encima como contorno rojo.

Cada hoja lleva título, leyenda (solo con lo visible), norte, barra de escala, escala
numérica, cuadrícula de coordenadas y una nota con proyecto, sistema de referencia,
fuentes y fecha.

![Mapa de ejemplo generado con los datos sintéticos de las pruebas](docs/ejemplo_mapa.png)

## Herramientas

| Herramienta | Qué hace |
|---|---|
| `ping` | Comprueba que QGIS y el complemento responden |
| `list_layer_types` | Lista las 15 capas, sus campos esperados y recortes por defecto |
| `inspect_dataset` | Muestra CRS, geometría, campos y valores de ejemplo de un archivo |
| `set_project_area` | Define el shape del proyecto (y opcionalmente el CRS de salida, p. ej. `EPSG:32615`) |
| `add_layer` | Agrega o reemplaza una capa temática a partir de un archivo vectorial o ráster |
| `remove_layer`, `reset_map`, `get_map_state` | Administran el mapa en construcción |
| `generate_map` | Una hoja con varias capas (PDF, PNG, JPG o TIF según la extensión), abierta en el diseñador de QGIS |
| `generate_map_series` | Una hoja por capa: Mapa de Zonas de Vida, Mapa de Cuencas, etc., cada una como diseño en QGIS |

En QGIS, `set_project_area` agrega el área como contorno rojo y encuadra el mapa;
`add_layer` coloca cada capa con su estilo en el grupo **Capas temáticas** según el
orden de dibujo; cada mapa generado crea un grupo oculto **Mapa: título** con las capas
recortadas y un diseño con el mismo título (generar de nuevo el mismo título lo
reemplaza).

Ejemplo de conversación: *"Usa `C:/proyecto/area.shp` como área del proyecto, agrega
zonas de vida, cuencas, ríos y volcanes de `C:/datos/`, y genera la serie de mapas en
A3 con ríos como referencia en cada hoja."*

## Instalación

Necesitas QGIS 3.28 o superior (probado con 3.34).

### 1. Complemento de QGIS

Desde una copia de este repositorio, con cualquier Python 3.10+:

```bash
pip install -e .
qgis-mcp-install-plugin            # o: python -m qgis_mcp.install_plugin --profile otro_perfil
```

Esto copia el paquete a la carpeta de complementos del perfil (`default`):

- Windows: `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\qgis_mcp`
- macOS: `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/qgis_mcp`
- Linux: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/qgis_mcp`

Reinicia QGIS y activa **QGIS MCP** en *Complementos ▸ Administrar e instalar
complementos*. El servidor del complemento se inicia solo (botón **QGIS MCP** en la
barra de herramientas para detenerlo; `QGIS_MCP_AUTOSTART=0` lo desactiva al abrir).

### 2. Servidor MCP

El servidor solo necesita Python 3.10+ y el paquete `mcp`; habla con QGIS por el socket.
En Claude Desktop (`claude_desktop_config.json`):

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

Variables opcionales: `QGIS_MCP_HOST`, `QGIS_MCP_PORT` (por defecto `9876`, también la
lee el complemento) y `QGIS_MCP_TIMEOUT` en segundos (por defecto `600`).

### Modo sin QGIS abierto

Con `"env": {"QGIS_MCP_MODE": "headless"}` el servidor usa PyQGIS directamente, así que
debe ejecutarse con el Python de QGIS: en Linux un entorno creado con
`python3 -m venv --system-site-packages` sobre `python3-qgis`; en Windows
`C:\Program Files\QGIS 3.34.4\bin\python-qgis.bat -m qgis_mcp`; en macOS el Python de
`QGIS.app` con `QGIS_PREFIX_PATH=/Applications/QGIS.app/Contents/MacOS`.

## Desarrollo

```bash
.venv/bin/pip install -e '.[test]'
.venv/bin/python -m pytest
```

Las pruebas crean datos sintéticos de las 15 capas alrededor de un proyecto ficticio en
Guatemala (`tests/sample_data.py`) y generan mapas reales con QGIS. `tests/test_plugin.py`
levanta el complemento sobre el proyecto de QGIS y le habla por el socket. Sin PyQGIS,
solo se ejecutan las pruebas del catálogo y del servidor.
