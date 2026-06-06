"""
JavaScript URI encode/decode global functions.

Usage:

```python
from pulse.js import encodeURIComponent

@ps.javascript
def example(value: str):
    return encodeURIComponent(value)
```
"""

from pulse.transpiler.js_module import JsModule


def encodeURI(uri: str, /) -> str: ...


def encodeURIComponent(uriComponent: str, /) -> str: ...


def decodeURI(encodedURI: str, /) -> str: ...


def decodeURIComponent(encodedURIComponent: str, /) -> str: ...


# Self-register this module as a JS builtin (global identifiers)
JsModule.register(name=None)
