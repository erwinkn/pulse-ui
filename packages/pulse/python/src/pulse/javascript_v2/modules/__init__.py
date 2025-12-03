"""Central registration point for all Python module transpilers.

This module registers all built-in Python modules for JavaScript transpilation.
Import this module to ensure all transpilers are available.
"""

import math as _math_module

from pulse.javascript_v2.module import register_module
from pulse.javascript_v2.modules.math import PyMath

# Register built-in Python modules
register_module(_math_module, PyMath)
