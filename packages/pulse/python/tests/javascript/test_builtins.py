from pulse.javascript.transpiler import compile_python_to_js


def test_len():
	def f(a):
		return len(a)

	code, _, _ = compile_python_to_js(f)
	assert code == (
		"""function(a){
return a.length ?? a.size;
}"""
	)


def test_divmod_builtin():
	def f(a, b):
		return divmod(a, b)

	code, _, _ = compile_python_to_js(f)
	assert code == (
		"""function(a, b){
return [Math.floor(a / b), a - Math.floor(a / b) * b];
}"""
	)


def test_round_negative_ndigits():
	def f(x):
		return round(x, -2)

	code, _, _ = compile_python_to_js(f)
	assert code == (
		"""function(x){
return Math.round(Number(x) / Math.pow(10, 2)) * Math.pow(10, 2);
}"""
	)


def test_round_runtime_ndigits():
	def f(x, n):
		return round(x, n)

	code, _, _ = compile_python_to_js(f)
	assert code == (
		"""function(x, n){
return n < 0 ? Math.round(Number(x) / Math.pow(10, Math.abs(n))) * Math.pow(10, Math.abs(n)) : Number(x).toFixed(n);
}"""
	)


def test_format_builtin():
	def f(x):
		return format(x, ".2f")

	code, _, _ = compile_python_to_js(f)
	assert code == (
		"""function(x){
return x.toFixed(2);
}"""
	)


def test_min():
	def f(a, b):
		return min(a, b)

	code, _, _ = compile_python_to_js(f)
	assert code == (
		"""function(a, b){
return Math.min(a, b);
}"""
	)


def test_max():
	def f(a, b):
		return max(a, b)

	code, _, _ = compile_python_to_js(f)
	assert code == (
		"""function(a, b){
return Math.max(a, b);
}"""
	)


def test_abs():
	def f(b):
		return abs(b)

	code, _, _ = compile_python_to_js(f)
	assert code == (
		"""function(b){
return Math.abs(b);
}"""
	)


def test_int_parse_literal():
	def f():
		return int(3.2)

	code, _, _ = compile_python_to_js(f)
	assert code == (
		"""function(){
return parseInt(3.2);
}"""
	)


def test_float_parse_literal():
	def f():
		return float("2.5")

	code, _, _ = compile_python_to_js(f)
	assert code == (
		"""function(){
return parseFloat("2.5");
}"""
	)


def test_round_and_str():
	def f(x):
		return str(round(x))

	code, _, _ = compile_python_to_js(f)
	assert code == (
		"""function(x){
return String(Math.round(x));
}"""
	)


def test_round_with_ndigits():
	def f(x):
		return round(x, ndigits=2)

	code, _, _ = compile_python_to_js(f)
	assert code == (
		"""function(x){
return Number(x).toFixed(2);
}"""
	)


def test_int_with_base16_keyword_args():
	def f(s: str):
		return int(s, 16)

	code, _, _ = compile_python_to_js(f)
	assert code == (
		"""function(s){
return parseInt(s, 16);
}"""
	)


def test_bool_builtin():
	def f(x):
		return bool(x)

	code, _, _ = compile_python_to_js(f)
	assert code == (
		"""function(x){
return Boolean(x);
}"""
	)


def test_set_empty_and_from_iterable():
	def g(a):
		return set()

	def h(a):
		return set(a)

	code_g, _, _ = compile_python_to_js(g)
	assert code_g == (
		"""function(a){
return new Set();
}"""
	)
	code_h, _, _ = compile_python_to_js(h)
	assert code_h == (
		"""function(a){
return new Set(a);
}"""
	)


def test_tuple_empty_and_from_iterable():
	def g(a):
		return tuple()

	def h(a):
		return tuple(a)

	code_g, _, _ = compile_python_to_js(g)
	assert code_g == (
		"""function(a){
return [];
}"""
	)
	code_h, _, _ = compile_python_to_js(h)
	assert code_h == (
		"""function(a){
return Array.from(a);
}"""
	)


def test_filter_truthy_none():
	def g(a):
		return filter(None, a)

	code_g, _, _ = compile_python_to_js(g)
	assert code_g == (
		"""function(a){
return a.filter(v => v);
}"""
	)


def test_reversed_builtin():
	def f(a):
		return reversed(a)

	code, _, _ = compile_python_to_js(f)
	assert code == (
		"""function(a){
return a.slice().reverse();
}"""
	)


def test_enumerate_builtin():
	def f(a):
		return enumerate(a)

	def g(a):
		return enumerate(a, 1)

	code_f, _, _ = compile_python_to_js(f)
	assert code_f == (
		"""function(a){
return a.map((v, i) => [i + 0, v]);
}"""
	)
	code_g, _, _ = compile_python_to_js(g)
	assert code_g == (
		"""function(a){
return a.map((v, i) => [i + 1, v]);
}"""
	)


def test_range_builtin():
	def a():
		return range(3)

	def b():
		return range(1, 5)

	def c():
		return range(1, 5, 2)

	code_a, _, _ = compile_python_to_js(a)
	assert code_a == (
		"""function(){
return Array.from(new Array(Math.max(0, 3)).keys());
}"""
	)
	code_b, _, _ = compile_python_to_js(b)
	assert code_b == (
		"""function(){
return Array.from(new Array(Math.max(0, Math.ceil((5 - 1) / 1))).keys(), i => 1 + i * 1);
}"""
	)
	code_c, _, _ = compile_python_to_js(c)
	assert code_c == (
		"""function(){
return Array.from(new Array(Math.max(0, Math.ceil((5 - 1) / 2))).keys(), i => 1 + i * 2);
}"""
	)


def test_sorted_builtin():
	def a(x):
		return sorted(x)

	code, _, _ = compile_python_to_js(a)
	assert code.startswith("function(x){\nreturn x.slice().sort(")


def test_zip_builtin():
	def a(x, y):
		return zip(x, y, strict=False)

	code, _, _ = compile_python_to_js(a)
	assert code.startswith(
		"function(x, y){\nreturn Array.from(new Array(Math.min(x.length, y.length)).keys(), i => [x[i], y[i]])"
	)


def test_pow_chr_ord_dict():
	def a(x, y):
		return pow(x, y)

	def b(n):
		return chr(n)

	def c(s):
		return ord(s)

	def d():
		return dict()

	def e(a):
		return dict(a)

	def f():
		return dict(a=1, b=2)

	ca, _, _ = compile_python_to_js(a)
	cb, _, _ = compile_python_to_js(b)
	cc, _, _ = compile_python_to_js(c)
	cd, _, _ = compile_python_to_js(d)
	ce, _, _ = compile_python_to_js(e)
	cf, _, _ = compile_python_to_js(f)
	assert ca == (
		"""function(x, y){
return Math.pow(x, y);
}"""
	)
	assert cb == (
		"""function(n){
return String.fromCharCode(n);
}"""
	)
	assert cc == (
		"""function(s){
return s.charCodeAt(0);
}"""
	)
	assert cd == (
		"""function(){
return new Map();
}"""
	)
	assert ce == (
		"""function(a){
return new Map(a);
}"""
	)
	assert cf == (
		"""function(){
return new Map([["a", 1], ["b", 2]]);
}"""
	)
