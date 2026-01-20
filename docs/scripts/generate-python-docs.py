#!/usr/bin/env python3
"""Generate Python API documentation for Pulse."""

import json
from pathlib import Path

import griffe
from fumapy.mksource import CustomEncoder, parse_module
from griffe_typingdoc import TypingDocExtension

MODULE = "pulse"


def main() -> None:
	out_dir = Path(__file__).parent.parent / "generated"
	out_dir.mkdir(exist_ok=True)

	extensions = griffe.load_extensions(TypingDocExtension)
	pkg = parse_module(
		griffe.load(
			MODULE,
			docstring_parser="auto",
			store_source=True,
			extensions=extensions,
		)
	)
	out_file = out_dir / f"{MODULE}.json"
	with open(out_file, "w") as file:
		json.dump(pkg, file, cls=CustomEncoder, indent=2, full=True)

	print(f"Generated {out_file}")


if __name__ == "__main__":
	main()
