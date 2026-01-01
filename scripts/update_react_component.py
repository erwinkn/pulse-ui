#!/usr/bin/env python3
import re
from pathlib import Path


def update_react_component_declarations(file_path: Path):
	"""Update @ps.react_component decorators with string args to use ps.Import(...)"""
	content = file_path.read_text()
	original_content = content

	# Pattern 1: Single-line @ps.react_component("ImportName", "src", prop="Prop")
	pattern_single = (
		r'@ps\.react_component\("([^"]+)",\s*"([^"]+)"(?:,\s*prop="([^"]+)")?\)'
	)

	def replace_func(match):
		import_name = match.group(1)
		src = match.group(2)
		prop_value = match.group(3) if match.group(3) else None

		# Build the Import() call
		if prop_value:
			import_expr = f'ps.Import("{import_name}", "{src}", prop="{prop_value}")'
		else:
			import_expr = f'ps.Import("{import_name}", "{src}")'

		return f"@ps.react_component({import_expr})"

	# Pattern 2: Multi-line @ps.react_component("ImportName", "src",\n    extra_imports=[...])
	pattern_multi = (
		r'@ps\.react_component\(\s*"([^"]+)",\s*"([^"]+)",\s*\n\s*extra_imports='
	)

	def replace_multi(match):
		import_name = match.group(1)
		src = match.group(2)
		import_expr = f'ps.Import("{import_name}", "{src}")'
		return f"@ps.react_component(\n\t{import_expr},\n\textra_imports="

	new_content = re.sub(pattern_single, replace_func, content)
	new_content = re.sub(pattern_multi, replace_multi, new_content)

	if new_content != original_content:
		file_path.write_text(new_content)
		return True
	return False


def main():
	# Find all Python files in packages that need updating
	base_dir = Path("/Users/erwin/Code/pulse-ui/packages")

	# Check packages
	packages_to_check = [
		"pulse-ag-grid",
		"pulse-mantine",
		"pulse-recharts",
	]

	count = 0
	for package_name in packages_to_check:
		package_path = base_dir / package_name
		if not package_path.exists():
			continue

		for py_file in package_path.rglob("*.py"):
			if update_react_component_declarations(py_file):
				count += 1
				print(f"Updated: {py_file}")

	print(f"\nUpdated {count} files")


if __name__ == "__main__":
	main()
