from typing import Any, override

import pytest
from pulse.app import App
from pulse.plugin import Plugin
from pulse.serializer import Serializer, SerializerAdapter


class Value:
	value: str

	def __init__(self, value: str) -> None:
		self.value = value


class PluginSerializer(Plugin):
	@override
	def serializer_adapters(self) -> list[SerializerAdapter[Any]]:
		return [SerializerAdapter(Value, lambda value: {"value": value.value})]


def test_plugin_serializer_adapters_reach_app_serializer() -> None:
	app = App(plugins=[PluginSerializer()])

	assert app.serializer.deserialize(app.serializer.serialize(Value("ok"))) == {
		"value": "ok"
	}


def test_plugin_serializer_adapters_merge_with_explicit_serializer() -> None:
	class Other:
		pass

	app = App(
		plugins=[PluginSerializer()],
		serializer=Serializer([SerializerAdapter(Other, lambda _: {"other": True})]),
	)

	assert app.serializer.deserialize(
		app.serializer.serialize({"value": Value("ok"), "other": Other()})
	) == {"value": {"value": "ok"}, "other": {"other": True}}


def test_plugin_serializer_adapter_duplicates_fail_early() -> None:
	with pytest.raises(ValueError, match="Duplicate serializer adapter target: Value"):
		App(
			plugins=[PluginSerializer()],
			serializer=Serializer(
				[SerializerAdapter(Value, lambda _: {"explicit": True})]
			),
		)
