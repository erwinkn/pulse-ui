from typing import Sequence

from .nodes import (
	JSArrowFunction,
	JSAssign,
	JSBlock,
	JSCall,
	JSConstAssign,
	JSExpr,
	JSIdentifier,
	JSNumber,
	JSStmt,
	JSUnary,
	is_primary,
)


def iife(body: JSExpr | Sequence[JSStmt | None]):
	if not isinstance(body, JSExpr):
		fn_body = JSBlock(list(filter(None, body)))
	else:
		fn_body = body

	return JSCall(JSArrowFunction("()", fn_body), [])


def const(ident: str, value: JSExpr):
	ident_expr = JSIdentifier(ident)
	return ident_expr, JSConstAssign(ident, value)


def let(ident: str, value: JSExpr):
	ident_expr = JSIdentifier(ident)
	return ident_expr, JSAssign(ident, value)


def define_if_not_primary(ident: str, expr: JSExpr):
	if is_primary(expr):
		return expr, None
	return const(ident, expr)


def extract_constant_number(nd_e: JSExpr):
	if isinstance(nd_e, JSNumber):
		return nd_e.value
	if isinstance(nd_e, JSUnary) and isinstance(nd_e.operand, JSNumber):
		if nd_e.op == "-":
			return -nd_e.operand.value
		if nd_e.op == "+":
			return nd_e.operand.value
	return None
