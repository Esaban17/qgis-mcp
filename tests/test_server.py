import asyncio
import json

import pytest

TOOLS = {
    "list_layer_types", "inspect_dataset", "set_project_area", "add_layer", "remove_layer",
    "reset_map", "get_map_state", "generate_map", "generate_map_series",
}


def _call(tool_name, **arguments):
    from qgis_mcp.server import mcp

    result = asyncio.run(mcp.call_tool(tool_name, arguments))
    assert not result.is_error, result.content[0].text
    return result.structured_content or json.loads(result.content[0].text)


def test_server_exposes_tools():
    from qgis_mcp.server import mcp

    assert TOOLS <= {tool.name for tool in asyncio.run(mcp.list_tools())}


def test_list_layer_types_tool():
    data = _call("list_layer_types")
    layers = data.get("result", data)
    assert len(layers) == 15


@pytest.mark.qgis
def test_end_to_end_through_tools(sample, tmp_path):
    _call("reset_map")
    area = _call("set_project_area", path=sample["area"], name="Proyecto Demo")
    assert area["crs"] == "EPSG:32615" and area["area_ha"] > 0
    added = _call("add_layer", layer_type="Zonas de Vida", path=sample["zonas_vida"])
    assert added["classify_by"] == "ZONA_VIDA"
    _call("add_layer", layer_type="volcanes", path=sample["volcanes"])
    state = _call("get_map_state")
    assert [layer["layer_type"] for layer in state["layers"]] == ["zonas_vida", "volcanes"]
    out = _call("generate_map", output_path=str(tmp_path / "mapa.pdf"), dpi=60)
    assert out["output"].endswith("mapa.pdf")
    _call("reset_map")


@pytest.mark.qgis
def test_add_layer_rolls_back_on_bad_field(sample):
    from qgis_mcp.server import mcp, session

    _call("reset_map")
    from mcp.server.mcpserver.exceptions import ToolError

    with pytest.raises(ToolError, match="NADA"):
        asyncio.run(mcp.call_tool("add_layer", {"layer_type": "rios", "path": sample["rios"], "field": "NADA"}))
    assert "rios" not in session.layers
