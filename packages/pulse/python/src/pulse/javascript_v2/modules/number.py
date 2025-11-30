from collections.abc import Sequence

from pulse.javascript_v2.constants import jsify
from pulse.javascript_v2.module import JsModule
from pulse.javascript_v2.nodes import (
	JSExpr,
	JSIdentifier,
	JSMember,
	JSMemberCall,
)


def NumberMethod(name: str, args: Sequence[JSExpr]):
	return JSMemberCall(JSIdentifier("Number"), name, args)


class Number(JsModule):
	# Static Methods
	@staticmethod
	def isFinite(value: int | float | str | JSExpr) -> JSExpr:
		return NumberMethod("isFinite", [jsify(value)])

	@staticmethod
	def isInteger(value: int | float | str | JSExpr) -> JSExpr:
		return NumberMethod("isInteger", [jsify(value)])

	@staticmethod
	def isNaN(value: int | float | str | JSExpr) -> JSExpr:
		return NumberMethod("isNaN", [jsify(value)])

	@staticmethod
	def isSafeInteger(value: int | float | str | JSExpr) -> JSExpr:
		return NumberMethod("isSafeInteger", [jsify(value)])

	@staticmethod
	def parseFloat(string: str | JSExpr) -> JSExpr:
		return NumberMethod("parseFloat", [jsify(string)])

	@staticmethod
	def parseInt(string: str | JSExpr, radix: int | JSExpr | None = None) -> JSExpr:
		if radix is None:
			return NumberMethod("parseInt", [jsify(string)])
		return NumberMethod("parseInt", [jsify(string), jsify(radix)])

	# Instance Methods (called as static methods with number as first arg)
	@staticmethod
	def toExponential(
		value: int | float | JSExpr,
		fractionDigits: int | JSExpr | None = None,
	) -> JSExpr:
		if fractionDigits is None:
			return JSMemberCall(jsify(value), "toExponential", [])
		return JSMemberCall(jsify(value), "toExponential", [jsify(fractionDigits)])

	@staticmethod
	def toFixed(
		value: int | float | JSExpr, digits: int | JSExpr | None = None
	) -> JSExpr:
		if digits is None:
			return JSMemberCall(jsify(value), "toFixed", [])
		return JSMemberCall(jsify(value), "toFixed", [jsify(digits)])

	@staticmethod
	def toPrecision(
		value: int | float | JSExpr,
		precision: int | JSExpr | None = None,
	) -> JSExpr:
		if precision is None:
			return JSMemberCall(jsify(value), "toPrecision", [])
		return JSMemberCall(jsify(value), "toPrecision", [jsify(precision)])

	@staticmethod
	def toString(
		value: int | float | JSExpr, radix: int | JSExpr | None = None
	) -> JSExpr:
		if radix is None:
			return JSMemberCall(jsify(value), "toString", [])
		return JSMemberCall(jsify(value), "toString", [jsify(radix)])

	@staticmethod
	def valueOf(value: int | float | JSExpr) -> JSExpr:
		return JSMemberCall(jsify(value), "valueOf", [])

	# Constants
	@staticmethod
	def EPSILON() -> JSExpr:
		return JSMember(JSIdentifier("Number"), "EPSILON")

	@staticmethod
	def MAX_SAFE_INTEGER() -> JSExpr:
		return JSMember(JSIdentifier("Number"), "MAX_SAFE_INTEGER")

	@staticmethod
	def MAX_VALUE() -> JSExpr:
		return JSMember(JSIdentifier("Number"), "MAX_VALUE")

	@staticmethod
	def MIN_SAFE_INTEGER() -> JSExpr:
		return JSMember(JSIdentifier("Number"), "MIN_SAFE_INTEGER")

	@staticmethod
	def MIN_VALUE() -> JSExpr:
		return JSMember(JSIdentifier("Number"), "MIN_VALUE")

	@staticmethod
	def NaN() -> JSExpr:
		return JSMember(JSIdentifier("Number"), "NaN")

	@staticmethod
	def NEGATIVE_INFINITY() -> JSExpr:
		return JSMember(JSIdentifier("Number"), "NEGATIVE_INFINITY")

	@staticmethod
	def POSITIVE_INFINITY() -> JSExpr:
		return JSMember(JSIdentifier("Number"), "POSITIVE_INFINITY")
