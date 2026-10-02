"""In-memory state of the map being assembled (pure Python)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from .catalog import ClipMode, LayerType, get_layer_type

VECTOR_SUFFIXES = {".shp", ".gpkg", ".geojson", ".json", ".kml", ".gml", ".fgb", ".sqlite", ".csv"}
RASTER_SUFFIXES = {".tif", ".tiff", ".img", ".asc", ".vrt", ".nc", ".jp2"}


def detect_kind(path: str | Path) -> str:
    """Guess whether a dataset is 'vector' or 'raster' from its extension."""
    suffix = Path(path).suffix.lower()
    if suffix in RASTER_SUFFIXES:
        return "raster"
    if suffix in VECTOR_SUFFIXES:
        return "vector"
    raise ValueError(f"Formato no soportado: {suffix or path!r}")


def _check_exists(path: str) -> str:
    resolved = Path(path).expanduser()
    if not resolved.exists():
        raise FileNotFoundError(f"No existe el archivo: {path}")
    return str(resolved.resolve())


@dataclass
class LayerEntry:
    layer_type: str
    path: str
    kind: str
    clip: ClipMode
    field: str | None = None
    label_field: str | None = None
    title: str | None = None
    subset: str | None = None

    @property
    def spec(self) -> LayerType:
        return get_layer_type(self.layer_type)

    @property
    def display_title(self) -> str:
        return self.title or self.spec.title


@dataclass
class ProjectArea:
    path: str
    name: str
    subset: str | None = None


@dataclass
class MapSession:
    area: ProjectArea | None = None
    layers: dict[str, LayerEntry] = field(default_factory=dict)
    crs: str | None = None

    def set_area(self, path: str, name: str | None = None, subset: str | None = None) -> ProjectArea:
        resolved = _check_exists(path)
        if detect_kind(resolved) != "vector":
            raise ValueError("El shape del proyecto debe ser una capa vectorial de polígonos.")
        self.area = ProjectArea(path=resolved, name=name or Path(resolved).stem, subset=subset)
        return self.area

    def add_layer(
        self,
        layer_type: str,
        path: str,
        field: str | None = None,
        label_field: str | None = None,
        clip: ClipMode | None = None,
        title: str | None = None,
        subset: str | None = None,
    ) -> LayerEntry:
        spec = get_layer_type(layer_type)
        resolved = _check_exists(path)
        if clip is not None and clip not in ("shape", "extent", "none"):
            raise ValueError("clip debe ser 'shape', 'extent' o 'none'.")
        entry = LayerEntry(
            layer_type=spec.key,
            path=resolved,
            kind=detect_kind(resolved),
            clip=clip or spec.clip,
            field=field,
            label_field=label_field,
            title=title,
            subset=subset,
        )
        self.layers[spec.key] = entry
        return entry

    def remove_layer(self, layer_type: str) -> None:
        key = get_layer_type(layer_type).key
        if key not in self.layers:
            raise KeyError(f"La capa {key!r} no está en el mapa.")
        del self.layers[key]

    def select(self, layer_types: list[str] | None) -> list[LayerEntry]:
        """Return the requested layers (all when None), bottom to top."""
        if layer_types is None:
            entries = list(self.layers.values())
        else:
            entries = []
            for name in layer_types:
                key = get_layer_type(name).key
                if key not in self.layers:
                    raise KeyError(f"La capa {key!r} no se ha agregado al mapa.")
                entries.append(self.layers[key])
        return sorted(entries, key=lambda e: e.spec.z)

    def require_area(self) -> ProjectArea:
        if self.area is None:
            raise RuntimeError("Primero define el shape del proyecto con set_project_area.")
        return self.area

    def to_dict(self) -> dict:
        return {
            "project_area": asdict(self.area) if self.area else None,
            "crs": self.crs,
            "layers": [
                {**asdict(entry), "title": entry.display_title}
                for entry in sorted(self.layers.values(), key=lambda e: e.spec.z)
            ],
        }
