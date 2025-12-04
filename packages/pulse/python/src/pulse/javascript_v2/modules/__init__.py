"""Central registration point for all Python module transpilers.

This module registers all built-in Python modules for JavaScript transpilation.
Import this module to ensure all transpilers are available.
"""

import math as math_builtin

import pulse.html.tags as pulse_tags
from pulse.javascript_v2.modules.math import PyMath
from pulse.javascript_v2.modules.tags import PyTags
from pulse.javascript_v2.py_module import register_module

# Register built-in Python modules
register_module(math_builtin, PyMath)

# Register Pulse HTML tags for JSX transpilation
register_module(pulse_tags, PyTags)
