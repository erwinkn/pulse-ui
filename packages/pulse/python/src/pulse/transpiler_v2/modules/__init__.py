"""Central registration point for all module transpilers.

This module registers all built-in Python modules for transpilation.
Import this module to ensure all transpilers are available.
"""

import asyncio as asyncio_builtin
import json as json_builtin
import math as math_builtin
import typing as typing_builtin

import pulse as pulse_module
import pulse.dom.tags as pulseTags
from pulse.transpiler_v2.modules.asyncio import PyAsyncio
from pulse.transpiler_v2.modules.json import PyJson
from pulse.transpiler_v2.modules.math import PyMath
from pulse.transpiler_v2.modules.pulse.tags import PulseTags
from pulse.transpiler_v2.modules.typing import PyTyping
from pulse.transpiler_v2.py_module import PyModule

# Register built-in Python modules
PyModule.register(math_builtin, PyMath)
PyModule.register(json_builtin, PyJson)
PyModule.register(asyncio_builtin, PyAsyncio)
PyModule.register(typing_builtin, PyTyping)

# Register Pulse DOM tags for JSX transpilation
# This covers `from pulse.dom import tags; tags.div(...)`
PyModule.register(pulseTags, PulseTags)

# Register main pulse module for transpilation
# This covers `import pulse as ps; ps.div(...)`
PyModule.register(pulse_module, PulseTags)
