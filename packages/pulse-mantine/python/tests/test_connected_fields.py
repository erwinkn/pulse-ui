from pulse.transpiler.imports import Import
from pulse.transpiler.nodes import Element
from pulse_mantine import CheckboxGroup, MultiSelect, TagsInput


def test_list_and_group_fields_use_pulse_mantine_wrappers():
	for component, name in (
		(MultiSelect, "MultiSelect"),
		(TagsInput, "TagsInput"),
		(CheckboxGroup, "CheckboxGroup"),
	):
		node = component(name="values")
		assert isinstance(node, Element)
		assert isinstance(node.tag, Import)
		assert node.tag.name == name
		assert node.tag.src == "pulse-mantine"
