"""JavaScript module bindings for use in @javascript decorated functions.

Usage:
    # For builtins (no import needed in JS):
    import pulse.js.math as Math
    Math.PI  # -> Math.PI

    from pulse.js.math import floor
    floor(x)  # -> Math.floor(x)

    # For external modules:
    from pulse.js.lodash import chunk
    chunk(arr, 2)  # -> import { chunk } from "lodash"; chunk(arr, 2)

    import pulse.js.lodash as _
    _.debounce(fn, 100)  # -> import _ from "lodash"; _.debounce(fn, 100)
"""
