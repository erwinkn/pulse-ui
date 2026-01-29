# Transpiler Scope Stack (Spec)

## Goal
- Correct Python name binding across nested functions/lambdas/comprehensions.
- Fix nested function name shadowing regression.
- Resolve locals independent of statement order.

## Non-goals
- Exact UnboundLocalError semantics (JS will differ).
- New statement support (class/with/import/match).
- global/nonlocal semantics (still error).

## Current gaps to fix
- Nested fn rebinding its own name reassigns outer const.
- Read-before-assign resolves to deps/builtins or errors.
- Locals assigned only in blocks (if/for/try) can be out of scope in JS.
- for-of uses const, so `x = ...` inside loop can throw.

## Scope model
- Scopes: function, lambda, comprehension.
- Function scope locals = params + assignment targets + for targets + except targets.
- Comprehension targets are local to comprehension scope only.
- def/class names bind in enclosing scope (not inside their own body).
- No block scopes for if/for/try (Python rule).

## Analysis pass
- Add ScopeAnalyzer that walks AST and builds Scope per function/lambda/comp.
- Scope fields: locals, assigned, params, declared (emit-time), parent.
- Map ast node -> Scope for emitter.

## Emission changes
- Transpiler uses scope_stack; self.locals removed.
- Name lookup:
  - if name in any scope.locals (walk out) -> Identifier
  - else deps -> builtins -> TranspileError
- Function prelude:
  - Emit `let a, b, c;` for locals in scope (exclude params).
  - Requires new Stmt node (e.g. LetDecl) to avoid `null` init.
- Assignments:
  - Name targets always local to current scope; emit plain assignment.
  - If target not in current scope.locals -> TranspileError (analysis bug).
- Nested function defs:
  - Name is a local in the enclosing scope (for recursion/outer refs).
  - Emit assignment `name = function(...) {}` (no const) to allow rebinding
    and avoid block-scoped defs.
- for-of:
  - Emit `for (x of iter)` / `for ([a, b] of iter)` (no const/let).
  - Targets are predeclared by scope prelude.
- Comprehensions:
  - Push comp scope for build; targets do not leak to outer scope.

## Error rules
- global/nonlocal -> TranspileError (explicit).
- Assignment to Name not in current scope.locals -> TranspileError.

## Tests to add/update
- Nested fn rebinds its own name (regression).
- for-loop target used after loop (should work).
- `x = x + 1` inside for-of (no const error).
- Use-before-assign resolves to local (JS may yield undefined).
- Shadowing between outer/inner/comprehension scopes.
- Update snapshot expectations for let/const changes + for-of output.

## Acceptance
- All transpiler tests updated, `make test` passes.
- Regression reproduced before, fixed after.
