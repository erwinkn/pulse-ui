import pytest
from pulse.transpiler_v2.nodes import Element, PulseNode


def test_element_flattens_nested_children():
	child = Element("span")
	node = Element("div", children=[["a", ["b"]], child])
	assert node.children == ["a", "b", child]


def test_element_rejects_dict_child():
	with pytest.raises(TypeError, match="Dict is not a valid child"):
		Element("div", children=[{"a": 1}])


def test_element_duplicate_keys_raise_in_dev(monkeypatch: pytest.MonkeyPatch):
	monkeypatch.setenv("PULSE_MODE", "dev")
	with pytest.raises(ValueError, match="Duplicate key 'dup'"):
		Element(
			"ul",
			children=[Element("li", key="dup"), Element("li", key="dup")],
		)


def test_pulsenode_bracket_warns_with_component_name(
	monkeypatch: pytest.MonkeyPatch,
):
	monkeypatch.setenv("PULSE_MODE", "dev")

	def render():
		return None

	node = PulseNode(fn=render, name="MyComponent")
	assert node.name == "MyComponent"
	items = [Element("span"), Element("span")]
	with pytest.warns(UserWarning, match=r"<MyComponent>"):
		result = node[items]
	assert result.args == tuple(items)
