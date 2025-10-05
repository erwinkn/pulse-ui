"""
Minimal AST-to-JS transpiler for a restricted, pure subset of Python used to
define synchronous JavaScript callbacks in the Pulse UI runtime.

The goal is to translate small Python functions into compact
JavaScript functions that can be inlined on the client where a sync
callback is required (e.g., chart formatters, sorters, small mappers).

The subset of the language supported is intended to be:
- Primitives (int, float, str, bool, datetime, None) and their methods
- Lists, tuples, sets, dicts, their constructor, their expressions, and their methods
- Core statements: return, if, elif, else, for, while, break, continue,
- Unary and binary operations, assignments, `in` operator
- Collections unpacking and comprehensions
- F-strings and the formatting mini-language
- Print (converted to console.log)
- Arbitrary JS objects with property access, method calling, and unpacking
- Lambdas (necessary for certain operations like filter, map, etc...)
- Built-in functions like `min`, `max`, `any`, `filter`, `sorted`
- Math module (later)
- Helpers, like deep equality (later)

The `@javascript` decorator compiles a function at definition-time and stores
metadata on the Python callable so the reconciler can send the compiled code to
the client.
"""
