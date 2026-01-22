# Error Handling

Exception classes, error propagation, and debugging in Pulse.

## Common Exceptions

### Channel Errors

```python
from pulse import ChannelClosed, ChannelTimeout

try:
    channel.emit("event", data)
except ChannelClosed:
    print("Channel was closed")

try:
    result = await channel.request("get_data", timeout=5.0)
except ChannelTimeout:
    print("Request timed out")
```

**ChannelClosed** - Raised when:
- Calling `emit()`, `request()`, or `on()` on a closed channel
- User navigates away or disconnects
- Component unmounts

**ChannelTimeout** - Raised when:
- `channel.request()` exceeds timeout waiting for client response
- Subclass of `asyncio.TimeoutError`

### JavaScript Execution Errors

```python
from pulse import run_js, JsExecError

@ps.javascript
def risky_operation():
    raise Error("Something failed")

async def handle_action():
    try:
        result = await run_js(risky_operation(), result=True)
    except JsExecError as e:
        print(f"JS error: {e}")
    except asyncio.TimeoutError:
        print("JS execution timed out")
```

**JsExecError** - Raised when client-side JS throws an exception.

### Transpiler Errors

```python
from pulse.transpiler.errors import TranspileError
```

**TranspileError** - Raised when Python-to-JS transpilation fails:
- Unsupported Python syntax
- Invalid `@ps.javascript` code
- Shows source location with line/column

### Routing Errors

```python
from pulse.routing import InvalidRouteError
```

**InvalidRouteError** - Raised for malformed route definitions.

### Render Loop Errors

```python
from pulse.render_session import RenderLoopError
```

**RenderLoopError** - Raised when a component exceeds the render limit (default 50) in a single reactive batch. Usually caused by:
- State update during render without guard
- Effect that triggers itself

### Hook Errors

```python
from pulse.hooks.core import HookError, HookNotFoundError
```

**HookError** - Base class for hook-related errors.
**HookNotFoundError** - Hook accessed before registration.

## Error Propagation

### Errors in Effects

Effects have an `on_error` parameter:

```python
from pulse.reactive import Effect

def my_effect():
    risky_operation()
    return lambda: print("cleanup")

def handle_error(exc: Exception):
    logger.error(f"Effect failed: {exc}")

effect = Effect(
    my_effect,
    on_error=handle_error,  # Catches errors
    name="my_effect",
)
```

Without `on_error`, exceptions propagate to the reactive context's error handler (if set) or re-raise.

**Cleanup on error:**
- Cleanup function runs before next execution, even after error
- Effect remains active after error (can re-run on next trigger)
- Use `effect.dispose()` to fully stop

### Errors in Callbacks

Event handler errors are reported to the client:

```python
def on_click():
    # If this raises, error is sent to client
    raise ValueError("Something wrong")

ps.button("Click", onClick=on_click)
```

Errors are:
1. Logged server-side
2. Sent to client as `server_error` message
3. For async callbacks, errors are caught when task completes

### Errors in Render

Render errors are caught and reported:

```python
@ps.component
def Broken():
    raise RuntimeError("Render failed")
    return ps.div("never")
```

The error is:
1. Logged with full traceback
2. Sent to client with phase="render"
3. Component tree may be partially rendered

## Query Error Handling

### Error Properties

```python
class DataState(ps.State):
    @ps.query
    async def data(self) -> dict:
        response = await api.fetch()
        if not response.ok:
            raise ValueError(f"API error: {response.status}")
        return response.json()

@ps.component
def DataView():
    with ps.init():
        state = DataState()

    if state.data.is_error:
        error = state.data.error  # Exception instance
        return ps.div(
            ps.p(f"Error: {error}"),
            ps.button("Retry", onClick=lambda: state.data.refetch()),
        )

    if state.data.is_loading:
        return ps.div("Loading...")

    return ps.div(str(state.data.data))
```

**Query error properties:**
- `is_error` - True if last fetch failed
- `error` - Exception instance or None
- `status` - "loading" | "success" | "error"

### on_error Callback

```python
class UserState(ps.State):
    @ps.query(retries=3, retry_delay=2.0)
    async def user(self) -> dict:
        return await api.get_user(self.user_id)

    @user.on_error
    def _on_error(self, error: Exception):
        # Called after all retries exhausted
        logger.error(f"Failed to load user: {error}")
        notify_user("Could not load user data")
```

The `on_error` callback:
- Runs after all retries fail
- Receives the final exception
- Can be sync or async

### Retry Behavior

```python
@ps.query(
    retries=3,         # Retry 3 times (default)
    retry_delay=2.0,   # Wait 2s between retries (default)
)
async def data(self) -> T: ...
```

Retry state is accessible:
```python
state.data.retries       # Current retry count (Signal)
state.data.retry_reason  # Last retry exception (Signal)
```

## Mutation Error Handling

```python
class UserState(ps.State):
    @ps.mutation
    async def update_name(self, name: str) -> dict:
        return await api.update_user(name=name)

    @update_name.on_error
    def _on_error(self, error: Exception):
        logger.error(f"Update failed: {error}")

# Usage - mutation re-raises error
async def save():
    try:
        result = await state.update_name("New Name")
    except Exception as e:
        show_error(f"Failed: {e}")
```

**Mutation error properties:**
- `error` - Last exception or None
- `is_running` - True during execution

## Client-Side Errors

### Network Errors

WebSocket disconnection is handled automatically:
- Messages queue during brief disconnects
- Reconnection attempts with backoff
- `RenderSession.connected` tracks connection state

### JS Execution Errors

When `run_js(..., result=True)` fails:

```python
async def action():
    try:
        result = await run_js(js_fn(), result=True, timeout=10.0)
    except JsExecError as e:
        # JS threw an error
        print(f"JS error: {e}")
    except asyncio.TimeoutError:
        # No response in time
        print("Timed out")
```

Fire-and-forget (`result=False`) errors are logged client-side only.

## Debugging Techniques

### Using websocket_id for Tracking

```python
@ps.component
def MyComponent():
    ws_id = ps.websocket_id()
    logger.info(f"Rendering for websocket {ws_id}")
    return ps.div(...)

# In callbacks
def on_action():
    ws_id = ps.websocket_id()
    logger.info(f"[{ws_id}] Action triggered")
```

Useful for:
- Correlating logs across requests
- Debugging multi-user issues
- Tracking session-specific problems

### Logging Patterns

```python
import logging
logger = logging.getLogger(__name__)

class DataState(ps.State):
    @ps.query
    async def data(self) -> dict:
        logger.debug(f"Fetching data for session {ps.session_id()}")
        try:
            result = await api.fetch()
            logger.info(f"Fetched {len(result)} items")
            return result
        except Exception as e:
            logger.exception(f"Fetch failed: {e}")
            raise

    @data.on_error
    def _on_error(self, error: Exception):
        logger.error(f"Query failed after retries: {error}")
```

### Common Error Messages

**"Internal error: PULSE_CONTEXT is not set"**
- Called Pulse function outside render/callback context
- Solution: Ensure code runs within component or callback

**"Channels require an active render session"**
- `ps.channel()` called outside component
- Solution: Create channels inside `ps.init()` or State.__init__

**"run_js() can only be called during callback execution"**
- `run_js()` called during render
- Solution: Move to event handler or effect

**"Detected an infinite render loop"**
- State update during render without guard
- Effect triggers itself
- Solution: Add conditional guards, check dependencies

**"@ps.effect decorator called multiple times at the same location"**
- Effect in loop without `key` parameter
- Solution: Add `@ps.effect(key=unique_value)`

**"Circular dependency detected"**
- Computed reads itself or creates cycle
- Solution: Restructure dependency graph

### Effect Error Debugging

```python
@ps.effect(
    on_error=lambda e: logger.exception(f"Effect error: {e}"),
    name="debug_effect",  # Named effects easier to track
)
def my_effect():
    # ... effect code
    pass
```

### Server Error Messages

Server errors sent to client include:
- `message` - Error string
- `stack` - Python traceback
- `phase` - "render", "callback", "effect", "navigate", "unmount"
- `details` - Additional context (callback name, effect name, etc.)

## Render Interrupts

Special exceptions for flow control (not errors):

```python
from pulse.hooks.runtime import RedirectInterrupt, NotFoundInterrupt

# In component render:
def protected_page():
    if not user:
        ps.redirect("/login")  # Raises RedirectInterrupt

def user_page():
    user = get_user(id)
    if not user:
        ps.not_found()  # Raises NotFoundInterrupt
```

These are caught by the framework and trigger navigation, not error handling.

## See Also

- `channels.md` - Channel lifecycle and error handling
- `queries.md` - Query retry and error states
- `reactive.md` - Effect error handling
- `js-interop.md` - run_js errors
