# Renderable payload serialization handoff

This plan adds first-class Pulse renderable payload support without using user-collidable sentinel objects. It treats expressions and JSX as Pulse-owned `VDOMNode` payloads tracked by serializer metadata.

## Goal

Allow Pulse-native renderables anywhere a server-to-client payload is serialized:

- `Expr` values serialize with `expr.render()`.
- `Element` values serialize as one-shot VDOM.
- `PulseNode` values serialize through a one-shot render pass.
- Plain JSON/data keeps current serializer behavior.

Primary motivating case:

```python
notifications.show(title=ps.span("Feedback"), message="Done", color="green")
```

This should not crash serialization, and the Mantine notification bridge should render `title` as the equivalent React node.

## Wire format

Extend serializer metadata out of band. Do not wrap payload subtrees in objects like `{"__pulse_vdom__": ...}`.

Current shape:

```python
((refs, dates, sets, maps), payload)
```

Proposed shape:

```python
((refs, dates, sets, maps, pulse_nodes), payload)
```

`pulse_nodes` stores global node indices whose payload entry is a Pulse `VDOMNode`.

This avoids collisions with user data. A user dict like this remains plain data:

```python
{"__pulse_vdom__": {"tag": "span"}}
```

## Pulse node model

Use one metadata list, not separate `exprs` and `vdoms`.

Reason: expressions and JSX both lower into the broader `VDOMNode` wire family:

```python
VDOMNode = primitive | VDOMElement | VDOMExpr
```

The distinction remains in the payload shape:

- `{"t": ...}` is a `VDOMExpr`.
- `{"tag": ...}` is a `VDOMElement`.
- primitives are plain VDOM primitive nodes.

The metadata says: this subtree is Pulse-owned and can be interpreted with Pulse VDOM rules.

## Serializer behavior

Add serializer support for Pulse-native values:

- `Expr` -> append current node index to `pulse_nodes`, payload is `expr.render()`.
- `Element` -> append current node index to `pulse_nodes`, payload is one-shot VDOM.
- `PulseNode` -> append current node index to `pulse_nodes`, payload is one-shot rendered VDOM.
- `Value` -> likely unwrap to `.value` before normal processing.

Keep generic JSON/date/set/ref behavior unchanged.

## One-shot render behavior

One-shot rendering is a snapshot. It does not create a persistent mounted Pulse subtree.

Allowed but inert after render:

- effects
- refs
- callbacks
- stateful components/hooks

Callbacks should be stripped from snapshot VDOM output. They must not emit `$cb` placeholders, because there is no persistent callback registry for this payload.

Immediate render-time work may still happen if existing render/hook behavior performs it during the render pass.

Implementation direction:

```python
Renderer(mode="persistent")  # current VDOM rendering
Renderer(mode="snapshot")    # serializer one-shot rendering
```

In snapshot mode, callback props are omitted instead of registered.

## Element API

Make `Element.render()` usable for one-shot VDOM:

```python
element.render()
element.render(renderer, path="")
```

If no renderer is provided, create a snapshot renderer and return a `VDOMNode`.

Keep a generic helper for payload serialization because `PulseNode` is not an `Element`:

```python
render_payload(value, renderer, path) -> JsonValue | VDOMNode
```

Watch for import cycles between `nodes.py` and `renderer.py`; use a local import or a narrow protocol if needed.

## Client deserialization

Deserializer should reconstruct Pulse-node metadata as branded internal values, not user-visible sentinel objects.

Conceptual TypeScript shape:

```ts
type PulseSerializedNode = {
  readonly [pulseNodeBrand]: true;
  readonly node: VDOMNode;
};
```

Consumers decide how to materialize:

- evaluate as JS expression
- render as React node
- leave opaque

Shape inspection is safe only after metadata proves the subtree is Pulse-owned.

## Message routing and registry context

Prefer routing messages to views first, then deserializing/hydrating inside the view.

Do not maintain a global `view -> registry` hydration map on the client.

Reasoning:

- Registries are naturally route-local.
- `PulseView` already owns the registry and `VDOMRenderer`.
- Future code splitting works better if route chunks own their registries.
- Hydration needs more than registry: renderer path, callback/ref behavior, cleanup/error ownership.

Client responsibility:

- shallow-route messages by `type` and `path`/`registryPath`
- deliver to the owning active view

View responsibility:

- deserialize Pulse-node metadata with its own renderer/registry context
- evaluate/render Pulse nodes where the receiving API expects them

For server-to-client messages that may carry Pulse nodes but are not naturally view-scoped, add an explicit `path` or `registryPath`.

## Server message implications

Existing server-to-client payload surfaces:

- `vdom_init`: already VDOM, route-scoped.
- `vdom_update`: already VDOM operations, route-scoped.
- `js_exec`: already route-scoped and expression-oriented.
- `channel_message`: currently generic and not route-scoped; needs `registryPath` if payloads can contain Pulse nodes.
- `api_call`: can technically serialize Pulse nodes if serializer allows it, but semantically it should remain fetch-body data unless a caller intentionally uses this feature.
- `server_error`, `navigate_to`, `reload`, `attach_ack`: control/diagnostic messages; no special hydration expected.

## Notification bridge

Once generic Pulse-node serialization exists, Pulse-Mantine notifications should not need a custom inline envelope.

Python side:

- `notifications.show/update/updateState` can pass payloads through the enhanced serializer.
- `onOpen`/`onClose` remain server callbacks tracked by notification id as today; do not serialize those functions.

JS side:

- The notification bridge receives deserialized branded Pulse nodes.
- For ReactNode fields like `title`, `message`, and `icon`, render Pulse nodes with the view renderer before calling Mantine `notifications.show/update/updateState`.
- Plain string notification payloads remain unchanged.

## Tests

Add focused tests for:

- User dict containing `{"__pulse_vdom__": ...}` remains plain data.
- Nested `Expr` serializes using `pulse_nodes` metadata.
- Nested `ps.span(...)` serializes using `pulse_nodes` metadata.
- Snapshot rendering strips callbacks from VDOM output.
- `notifications.show(title=ps.span("Feedback"), message="Done")` emits a serializable payload.
- JS notification bridge renders a deserialized Pulse node into a React node before passing it to Mantine.
- Plain string notification payloads still work.
- Generic channel payloads can carry Pulse nodes without serializer crashes, but hydration is view/bridge-owned.
- Route-local imported component payloads hydrate only with the correct view registry.

## Open decisions

- Exact serializer versioning/migration path for adding `pulse_nodes` metadata.
- Whether client deserialization should eagerly brand Pulse nodes or leave raw VDOM plus side metadata until view hydration.
- Exact server API for adding `registryPath` to `channel_message`.
- Whether snapshot mode should strip refs entirely or preserve inert ref-shaped props where harmless.
