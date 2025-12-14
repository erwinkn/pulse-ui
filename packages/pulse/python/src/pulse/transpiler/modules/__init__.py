"""Central registration point for all module transpilers.

This module registers all built-in Python and JavaScript modules for transpilation.
Import this module to ensure all transpilers are available.
"""

import asyncio as asyncio_builtin
import json as json_builtin
import math as math_builtin
import re as re_builtin
import typing as typing_builtin

import pulse.dom.tags as pulse_tags
from pulse.transpiler.modules.asyncio import PyAsyncio
from pulse.transpiler.modules.json import PyJson
from pulse.transpiler.modules.math import PyMath
from pulse.transpiler.modules.re import PyRe
from pulse.transpiler.modules.tags import PyTags
from pulse.transpiler.modules.typing import PyTyping
from pulse.transpiler.py_module import register_module

# Register built-in Python modules
register_module(asyncio_builtin, PyAsyncio)
register_module(json_builtin, PyJson)
register_module(math_builtin, PyMath)
register_module(re_builtin, PyRe)
register_module(typing_builtin, PyTyping)

# Register Pulse HTML tags for JSX transpilation
register_module(pulse_tags, PyTags)
