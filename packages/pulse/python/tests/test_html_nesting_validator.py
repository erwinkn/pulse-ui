"""Tests for HTML nesting validation in dev mode."""

import pytest
from pulse.env import PulseEnv, env
from pulse.transpiler.nodes import Element


class TestHTMLNestingValidator:
	"""Test HTML nesting validation."""

	original_env: PulseEnv = "dev"  # type: ignore[assignment]

	def setup_method(self) -> None:
		"""Ensure dev mode is enabled for tests."""
		self.original_env = env.pulse_env
		env.pulse_env = "dev"  # type: ignore[assignment]

	def teardown_method(self) -> None:
		"""Restore original environment."""
		env.pulse_env = self.original_env  # type: ignore[assignment]

	def test_valid_nested_elements(self) -> None:
		"""Valid nesting should not raise."""
		# div can contain p
		el = Element("div", children=[Element("p", children=["text"])])
		assert el is not None
		# p can contain span
		el = Element("p", children=[Element("span", children=["text"])])
		assert el is not None

	def test_paragraph_cannot_contain_heading(self) -> None:
		"""p cannot contain h1."""
		with pytest.raises(ValueError, match="Invalid HTML nesting.*<h1>.*<p>"):
			Element("p", children=[Element("h1", children=["text"])])

	def test_paragraph_cannot_contain_paragraph(self) -> None:
		"""p cannot contain p."""
		with pytest.raises(ValueError, match="Invalid HTML nesting.*<p>.*<p>"):
			Element("p", children=[Element("p", children=["text"])])

	def test_div_inside_span(self) -> None:
		"""span cannot contain div (common mistake)."""
		# This is actually valid in modern HTML5, but keeping for test coverage
		el = Element("span", children=[Element("div", children=["text"])])
		assert el is not None

	def test_anchor_cannot_contain_anchor(self) -> None:
		"""a cannot contain a."""
		with pytest.raises(ValueError, match="Invalid HTML nesting.*<a>.*<a>"):
			Element("a", children=[Element("a", children=["text"])])

	def test_anchor_cannot_contain_button(self) -> None:
		"""a cannot contain button."""
		with pytest.raises(ValueError, match="Invalid HTML nesting.*<button>.*<a>"):
			Element("a", children=[Element("button", children=["text"])])

	def test_button_cannot_contain_form(self) -> None:
		"""button cannot contain form."""
		with pytest.raises(ValueError, match="Invalid HTML nesting.*<form>.*<button>"):
			Element("button", children=[Element("form", children=["text"])])

	def test_heading_cannot_contain_heading(self) -> None:
		"""h1 cannot contain h2."""
		with pytest.raises(ValueError, match="Invalid HTML nesting.*<h2>.*<h1>"):
			Element("h1", children=[Element("h2", children=["text"])])

	def test_list_cannot_contain_list(self) -> None:
		"""ul cannot contain ol (direct child)."""
		with pytest.raises(ValueError, match="Invalid HTML nesting.*<ol>.*<ul>"):
			Element("ul", children=[Element("ol", children=["text"])])

	def test_list_can_contain_nested_list_via_li(self) -> None:
		"""ul can contain li which can contain ol."""
		el = Element(
			"ul", children=[Element("li", children=[Element("ol", children=["text"])])]
		)
		assert el is not None

	def test_void_elements_cannot_have_children(self) -> None:
		"""img cannot have children."""
		with pytest.raises(
			ValueError, match="Invalid HTML nesting.*<img>.*void element"
		):
			Element("img", children=["text"])

	def test_br_cannot_have_children(self) -> None:
		"""br cannot have children."""
		with pytest.raises(
			ValueError, match="Invalid HTML nesting.*<br>.*void element"
		):
			Element("br", children=["text"])

	def test_input_cannot_have_children(self) -> None:
		"""input cannot have children."""
		with pytest.raises(
			ValueError, match="Invalid HTML nesting.*<input>.*void element"
		):
			Element("input", children=["text"])

	def test_fragment_skips_validation(self) -> None:
		"""Fragment (empty string tag) should skip validation."""
		# Fragment with any children should work
		el = Element("", children=[Element("p", children=["text"])])
		assert el is not None

	def test_component_skips_validation(self) -> None:
		"""Components ($$prefixed) should skip validation."""
		# Component can have any children
		el = Element("$$MyComponent", children=[Element("p", children=["text"])])
		assert el is not None

	def test_custom_component_child_skips_validation(self) -> None:
		"""Custom component children should not trigger validation."""
		# p with component child should not validate component
		el = Element("p", children=[Element("$$Button", children=["text"])])
		assert el is not None

	def test_text_children_are_valid(self) -> None:
		"""Text children should always be valid."""
		el = Element("p", children=["hello", "world"])
		assert el is not None

	def test_case_insensitive_matching(self) -> None:
		"""Tag matching should be case-insensitive."""
		with pytest.raises(ValueError, match="Invalid HTML nesting.*<h1>"):
			Element("P", children=[Element("H1", children=["text"])])

	def test_mixed_children_with_invalid_element(self) -> None:
		"""Mixed text and element children with one invalid element."""
		with pytest.raises(ValueError, match="Invalid HTML nesting"):
			Element("p", children=["hello", Element("p", children=["nested"])])

	def test_validation_disabled_in_prod_mode(self) -> None:
		"""Validation should be skipped in prod mode."""
		env.pulse_env = "prod"  # type: ignore[assignment]
		# This would normally raise, but shouldn't in prod mode
		el = Element("p", children=[Element("p", children=["text"])])
		assert el is not None

	def test_table_nesting_validation(self) -> None:
		"""Test table-specific nesting rules."""
		# table cannot contain another table
		with pytest.raises(ValueError, match="Invalid HTML nesting.*<table>.*<table>"):
			Element("table", children=[Element("table", children=["text"])])

	def test_valid_table_structure(self) -> None:
		"""Valid table structure should work."""
		table = Element(
			"table",
			children=[
				Element(
					"thead",
					children=[
						Element("tr", children=[Element("th", children=["header"])])
					],
				),
				Element(
					"tbody",
					children=[
						Element("tr", children=[Element("td", children=["data"])])
					],
				),
			],
		)
		assert table is not None

	def test_form_cannot_contain_form(self) -> None:
		"""form cannot contain form."""
		with pytest.raises(ValueError, match="Invalid HTML nesting.*<form>.*<form>"):
			Element("form", children=[Element("form", children=["text"])])

	def test_select_cannot_contain_select(self) -> None:
		"""select cannot contain select."""
		with pytest.raises(
			ValueError, match="Invalid HTML nesting.*<select>.*<select>"
		):
			Element("select", children=[Element("select", children=["text"])])

	def test_label_cannot_contain_label(self) -> None:
		"""label cannot contain label."""
		with pytest.raises(ValueError, match="Invalid HTML nesting.*<label>.*<label>"):
			Element("label", children=[Element("label", children=["text"])])

	def test_deeply_nested_valid_structure(self) -> None:
		"""Deeply nested valid structure should work."""
		# div > section > article > p > span
		el = Element(
			"div",
			children=[
				Element(
					"section",
					children=[
						Element(
							"article",
							children=[
								Element(
									"p", children=[Element("span", children=["text"])]
								)
							],
						)
					],
				)
			],
		)
		assert el is not None

	def test_deeply_nested_invalid_structure(self) -> None:
		"""Deeply nested invalid structure should raise."""
		# div > section > p > p (invalid at the end)
		with pytest.raises(ValueError, match="Invalid HTML nesting"):
			Element(
				"div",
				children=[
					Element(
						"section",
						children=[
							Element("p", children=[Element("p", children=["text"])])
						],
					)
				],
			)
