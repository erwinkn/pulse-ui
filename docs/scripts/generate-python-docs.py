#!/usr/bin/env python3
"""Generate Python API documentation for Pulse.

This script wraps fumapy to handle the pulse -> pulse-framework name mapping.
"""

import json
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import griffe
from fumapy.mksource import CustomEncoder
from fumapy.mksource import parse_module as _parse_module
from fumapy.mksource.models import Module
from griffe_typingdoc import TypingDocExtension


def parse_module(m: griffe.Object) -> Module:
	"""Parse module with custom version handling for pulse-framework."""
	result = (
		_parse_module.__wrapped__(m) if hasattr(_parse_module, "__wrapped__") else None
	)

	# If _parse_module doesn't have __wrapped__, we need to do it ourselves
	if result is None:
		from fumapy.mksource.simplify_docstring import simplify_docstring

		if not isinstance(m, griffe.Module):
			raise ValueError("Module must be a module")

		out = simplify_docstring(m.docstring, m)
		result: Module = {
			"name": m.name,
			"path": m.path,
			"filepath": m.filepath,
			"description": out.description,
			"docstring": out.remainder,
			"attributes": out.attributes,
			"modules": {
				name: parse_module(value)
				for name, value in m.modules.items()
				if not value.is_alias
			},
			"classes": {
				name: parse_class(value)
				for name, value in m.classes.items()
				if not value.is_alias
			},
			"functions": {
				name: parse_function(value)
				for name, value in m.functions.items()
				if not value.is_alias
			},
		}

	# Handle version lookup with fallback for pulse -> pulse-framework
	if m.is_package:
		try:
			result["version"] = version(m.name)
		except PackageNotFoundError:
			# Try pulse-framework for pulse module
			if m.name == "pulse":
				try:
					result["version"] = version("pulse-framework")
				except PackageNotFoundError:
					result["version"] = "unknown"
			else:
				result["version"] = "unknown"

	return result


def parse_class(c: griffe.Class):
	from fumapy.mksource.document_module import parse_class as _parse_class

	return _parse_class(c)


def parse_function(f: griffe.Function):
	from fumapy.mksource.document_module import parse_function as _parse_function

	return _parse_function(f)


def main():
	out_dir = Path(__file__).parent.parent / "generated"
	out_dir.mkdir(exist_ok=True)

	extensions = griffe.load_extensions(TypingDocExtension)

	pkg = parse_module(
		griffe.load(
			"pulse",
			docstring_parser="auto",
			store_source=True,
			extensions=extensions,
		)
	)

	out_file = out_dir / "pulse.json"
	with open(out_file, "w") as f:
		json.dump(pkg, f, cls=CustomEncoder, indent=2)

	print(f"Generated {out_file}")


if __name__ == "__main__":
	main()
