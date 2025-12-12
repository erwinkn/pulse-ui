from pulse.js2 import document
from pulse.transpiler_v2.function import analyze_deps


def test():
	return document.querySelector("div")


deps = analyze_deps(test)
print("document in deps:", "document" in deps)
if "document" in deps:
	print("document type:", type(deps["document"]))
	print("document:", deps["document"])
