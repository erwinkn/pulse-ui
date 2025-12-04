"""Central registration point for all module transpilers.

This module registers all built-in Python and JavaScript modules for transpilation.
Import this module to ensure all transpilers are available.
"""

import math as math_builtin

import pulse.html.tags as pulse_tags
import pulse.js.math as js_math
import pulse.js.number as js_number
from pulse.javascript_v2.js_module import register_js_module
from pulse.javascript_v2.modules.math import PyMath
from pulse.javascript_v2.modules.tags import PyTags
from pulse.javascript_v2.py_module import register_module

# Register built-in Python modules
register_module(math_builtin, PyMath)

# Register Pulse HTML tags for JSX transpilation
register_module(pulse_tags, PyTags)

# Register JavaScript builtins
register_js_module(js_math, name="Math")
register_js_module(js_number, name="Number")
