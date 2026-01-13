"""Dynamic import primitive for code-splitting.

Provides `import_` for inline dynamic imports in @javascript functions:

    @javascript
    def load_chart():
        return import_("./Chart").then(lambda m: m.default)

For lazy-loaded React components, use Import(lazy=True) with React.lazy:

    from pulse.js.react import React, lazy

    # Low-level: Import(lazy=True) creates a factory, wrap with React.lazy
    factory = Import("Chart", "./Chart", kind="default", lazy=True)
    LazyChart = Jsx(React.lazy(factory))

    # High-level: lazy() helper combines both
    LazyChart = lazy("./Chart")
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import TYPE_CHECKING, override

from pulse.transpiler.assets import LocalAsset, register_local_asset
from pulse.transpiler.errors import TranspileError
from pulse.transpiler.imports import is_local_path, resolve_local_path
from pulse.transpiler.nodes import Expr, Member
from pulse.transpiler.vdom import VDOMNode

if TYPE_CHECKING:
	from pulse.transpiler.transpiler import Transpiler


@dataclass(slots=True)
class DynamicImport(Expr):
	"""Represents a dynamic import() expression.

	Emits as: import("src")

	Supports method chaining for .then():
	    import_("./foo").then(lambda m: m.bar)
	    -> import("./foo").then(m => m.bar)
	"""

	src: str
	asset: LocalAsset | None = None

	@override
	def emit(self, out: list[str]) -> None:
		if self.asset:
			out.append(f'import("{self.asset.import_path()}")')
		else:
			out.append(f'import("{self.src}")')

	@override
	def render(self) -> VDOMNode:
		raise TypeError("DynamicImport cannot be rendered to VDOM")

	@override
	def transpile_getattr(self, attr: str, ctx: Transpiler) -> Expr:
		"""Allow .then() and other method chaining."""
		return Member(self, attr)


class DynamicImportFn(Expr):
	"""Sentinel expr that intercepts import_() calls.

	When used in a @javascript function:
	    import_("./module")

	Transpiles to:
	    import("./module")

	For local paths, resolves the file and registers it for asset copying.
	"""

	@override
	def emit(self, out: list[str]) -> None:
		raise TypeError(
			"import_ cannot be emitted directly - call it with a source path"
		)

	@override
	def render(self) -> VDOMNode:
		raise TypeError("import_ cannot be rendered to VDOM")

	@override
	def transpile_call(
		self,
		args: list[ast.expr],
		keywords: list[ast.keyword],
		ctx: Transpiler,
	) -> Expr:
		"""Handle import_("source") calls."""
		if keywords:
			raise TranspileError("import_() does not accept keyword arguments")
		if len(args) != 1:
			raise TranspileError("import_() takes exactly 1 argument")

		# Extract string literal from AST
		src_node = args[0]
		if not isinstance(src_node, ast.Constant) or not isinstance(
			src_node.value, str
		):
			raise TranspileError("import_() argument must be a string literal")

		src = src_node.value
		asset: LocalAsset | None = None

		# Resolve local paths and register asset
		if is_local_path(src):
			if ctx.source_file is None:
				raise TranspileError(
					"Cannot resolve relative import_() path: source file unknown"
				)
			source_path = resolve_local_path(src, ctx.source_file)
			if source_path:
				asset = register_local_asset(source_path)

		return DynamicImport(src, asset)


# Singleton for use in deps
import_ = DynamicImportFn()
