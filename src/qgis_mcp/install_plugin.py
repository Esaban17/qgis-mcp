"""Copy this package into the QGIS plugins folder so QGIS loads it as a plugin."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

PLUGIN_NAME = "qgis_mcp"


def default_plugins_dir(profile: str = "default") -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ["APPDATA"]) / "QGIS" / "QGIS3"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "QGIS" / "QGIS3"
    else:
        base = Path.home() / ".local" / "share" / "QGIS" / "QGIS3"
    return base / "profiles" / profile / "python" / "plugins"


def install(plugins_dir: Path) -> Path:
    source = Path(__file__).resolve().parent
    target = plugins_dir / PLUGIN_NAME
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return target


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="default", help="Perfil de QGIS (por defecto: default)")
    parser.add_argument("--plugins-dir", type=Path, help="Carpeta de complementos, si no es la estándar")
    args = parser.parse_args(argv)
    target = install(args.plugins_dir or default_plugins_dir(args.profile))
    print(f"Complemento instalado en {target}")
    print("Reinicia QGIS y activa 'QGIS MCP' en Complementos > Administrar e instalar complementos.")


if __name__ == "__main__":
    main()
