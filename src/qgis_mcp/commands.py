"""Map commands shared by the QGIS plugin and the headless server.

``MapCommands()`` works on its own, without a QGIS window. Inside QGIS the
plugin builds it with the open project and ``iface``: the project shape and
every thematic layer then appear on the canvas as they are added, and each
generated map leaves its layout in the project's Layout Manager.
"""

from __future__ import annotations

from .catalog import LAYER_TYPES, get_layer_type
from .qgis_env import ensure_qgis
from .session import MapSession

THEMATIC_GROUP = "Capas temáticas"


class MapCommands:
    def __init__(self, project=None, iface=None):
        self.project = project
        self.iface = iface
        self.session = MapSession()
        # Layer ids this object put in the live project, keyed by layer type
        # ("__area__" for the project shape).
        self._live_ids: dict[str, str] = {}

    @property
    def live(self) -> bool:
        return self.project is not None

    def handlers(self) -> dict:
        return {
            "ping": self.ping,
            "list_layer_types": self.list_layer_types,
            "inspect_dataset": self.inspect_dataset,
            "set_project_area": self.set_project_area,
            "add_layer": self.add_layer,
            "remove_layer": self.remove_layer,
            "reset_map": self.reset_map,
            "get_map_state": self.get_map_state,
            "generate_map": self.generate_map,
            "generate_map_series": self.generate_map_series,
        }

    # --- Commands -----------------------------------------------------------

    def ping(self) -> dict:
        ensure_qgis()
        from qgis.core import Qgis

        return {"qgis": Qgis.QGIS_VERSION, "live": self.live}

    def list_layer_types(self) -> list[dict]:
        return [lt.to_dict() for lt in LAYER_TYPES]

    def inspect_dataset(self, path: str) -> dict:
        ensure_qgis()
        from .data import inspect

        return inspect(path)

    def set_project_area(self, path: str, name=None, crs=None, subset=None) -> dict:
        ensure_qgis()
        from qgis.core import QgsCoordinateReferenceSystem

        from .data import area_geometry, load_vector

        layer = load_vector(path, name, subset)
        target = QgsCoordinateReferenceSystem(crs) if crs else layer.crs()
        if not target.isValid():
            raise ValueError(f"Sistema de referencia inválido: {crs}")
        geom = area_geometry(layer, target)
        area = self.session.set_area(path, name, subset)
        self.session.crs = crs
        if self.live:
            self._show_area(layer, area.name, target if crs else None)
        box = geom.boundingBox()
        return {
            "project_area": area.name,
            "crs": target.authid(),
            "area_ha": round(geom.area() / 10_000, 2) if not target.isGeographic() else None,
            "extent": [box.xMinimum(), box.yMinimum(), box.xMaximum(), box.yMaximum()],
        }

    def add_layer(self, layer_type: str, path: str, field=None, label_field=None, clip=None, title=None, subset=None) -> dict:
        from .renderer import validate_layer

        key = get_layer_type(layer_type).key
        previous = self.session.layers.get(key)
        entry = self.session.add_layer(layer_type, path, field, label_field, clip, title, subset)
        try:
            details = validate_layer(entry)
            if self.live:
                self._show_layer(entry)
        except Exception:
            if previous is not None:
                self.session.layers[key] = previous
            else:
                self.session.layers.pop(key, None)
            raise
        return {"layer_type": key, "title": entry.display_title, "clip": entry.clip, **details}

    def remove_layer(self, layer_type: str) -> dict:
        key = get_layer_type(layer_type).key
        self.session.remove_layer(key)
        self._drop_live(key)
        return self.session.to_dict()

    def reset_map(self) -> dict:
        for key in list(self._live_ids):
            self._drop_live(key)
        self.session.area = None
        self.session.crs = None
        self.session.layers.clear()
        return self.session.to_dict()

    def get_map_state(self) -> dict:
        return self.session.to_dict()

    def generate_map(self, output_path: str, layers=None, page_size="A4", extent="project", open_layout=True, **options) -> dict:
        from .renderer import render_map

        result = render_map(
            self.session,
            output_path,
            layer_types=layers,
            page=page_size,
            extent_mode=extent,
            project=self.project,
            **options,
        )
        if self.live and open_layout and self.iface is not None:
            layout = self.project.layoutManager().layoutByName(result["layout"])
            if layout is not None:
                self.iface.openLayoutDesigner(layout)
        return result

    def generate_map_series(self, output_dir: str, format="pdf", layers=None, context_layers=None, page_size="A4", **options) -> dict:
        from .renderer import render_series

        return render_series(
            self.session,
            output_dir,
            fmt=format,
            layer_types=layers,
            context_layers=context_layers,
            page=page_size,
            project=self.project,
            **options,
        )

    # --- Live project ---------------------------------------------------------

    def _show_area(self, layer, name: str, crs) -> None:
        from .styling import style_project_area

        self._drop_live("__area__")
        layer.setName(f"Área del proyecto: {name}")
        style_project_area(layer)
        self.project.addMapLayer(layer, False)
        self.project.layerTreeRoot().insertLayer(0, layer)
        self._live_ids["__area__"] = layer.id()
        if crs is not None or not self.project.crs().isValid():
            self.project.setCrs(crs or layer.crs())
        if self.iface is not None:
            from .data import buffered_extent, layer_extent

            canvas = self.iface.mapCanvas()
            canvas.setExtent(buffered_extent(layer_extent(layer, self.project.crs()), 10))
            canvas.refresh()

    def _show_layer(self, entry) -> None:
        from qgis.core import QgsRasterLayer

        from .data import load
        from .styling import apply_labels, style_raster, style_vector

        self._drop_live(entry.layer_type)
        layer = load(entry.path, entry.display_title, entry.subset)
        if isinstance(layer, QgsRasterLayer):
            style_raster(layer, entry.spec)
        else:
            style_vector(layer, entry.spec, entry.field)
            apply_labels(layer, entry.spec, entry.label_field)
        root = self.project.layerTreeRoot()
        group = root.findGroup(THEMATIC_GROUP)
        if group is None:
            area_node = root.findLayer(self._live_ids.get("__area__", ""))
            group = root.insertGroup(1 if area_node is not None else 0, THEMATIC_GROUP)
        self.project.addMapLayer(layer, False)
        # Keep the group sorted by the catalog's drawing order, top first.
        ordered = sorted(
            (k for k in self._live_ids if k != "__area__" and k in self.session.layers),
            key=lambda k: -self.session.layers[k].spec.z,
        )
        position = sum(1 for k in ordered if self.session.layers[k].spec.z > entry.spec.z)
        group.insertLayer(position, layer)
        self._live_ids[entry.layer_type] = layer.id()

    def _drop_live(self, key: str) -> None:
        layer_id = self._live_ids.pop(key, None)
        if layer_id and self.live and self.project.mapLayer(layer_id) is not None:
            self.project.removeMapLayer(layer_id)
