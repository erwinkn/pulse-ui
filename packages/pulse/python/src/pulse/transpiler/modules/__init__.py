"""Central registration point for all module transpilers.

This module registers all built-in Python and JavaScript modules for transpilation.
Import this module to ensure all transpilers are available.
"""

import math as math_builtin

import pulse.html.tags as pulse_tags
from pulse.transpiler.modules.math import PyMath
from pulse.transpiler.modules.tags import PyTags
from pulse.transpiler.py_module import register_module

# Register built-in Python modules
register_module(math_builtin, PyMath)

# Register Pulse HTML tags for JSX transpilation
register_module(pulse_tags, PyTags)
