from typing import Any, TypedDict, Literal

from pulse.diff import VDOMOperation
from pulse.vdom import VDOM
from pulse.routing import RouteInfo


# ====================
# Server messages
# ====================
class ServerInitMessage(TypedDict):
    type: Literal["vdom_init"]
    path: str
    vdom: VDOM


class ServerUpdateMessage(TypedDict):
    type: Literal["vdom_update"]
    path: str
    ops: list[VDOMOperation]


class ServerErrorInfo(TypedDict, total=False):
    # High-level human message
    message: str
    # Full stack trace string (server formatted)
    stack: str
    # Which phase failed
    phase: Literal["render", "callback", "mount", "unmount", "navigate", "server"]
    # Optional extra details (callback key, etc.)
    details: dict[str, Any]


class ServerErrorMessage(TypedDict):
    type: Literal["server_error"]
    path: str
    error: ServerErrorInfo


class ServerNavigateToMessage(TypedDict):
    type: Literal["navigate_to"]
    path: str


class ServerApiCallMessage(TypedDict):
    type: Literal["api_call"]
    # Correlation id to match request/response
    id: str
    url: str
    method: str
    headers: dict[str, str]
    # Body can be JSON-serializable or None
    body: Any | None
    # Whether to include credentials (cookies)
    credentials: Literal["include", "omit"]


ServerMessage = (
    ServerInitMessage
    | ServerUpdateMessage
    | ServerErrorMessage
    | ServerApiCallMessage
    | ServerNavigateToMessage
)


# ====================
# Client messages
# ====================
class ClientCallbackMessage(TypedDict):
    type: Literal["callback"]
    path: str
    callback: str
    args: list[Any]


class ClientMountMessage(TypedDict):
    type: Literal["mount"]
    path: str
    routeInfo: RouteInfo


class ClientNavigateMessage(TypedDict):
    type: Literal["navigate"]
    path: str
    routeInfo: RouteInfo


class ClientUnmountMessage(TypedDict):
    type: Literal["unmount"]
    path: str


class ClientApiResultMessage(TypedDict):
    type: Literal["api_result"]
    id: str
    ok: bool
    status: int
    headers: dict[str, str]
    body: Any | None


ClientMessage = (
    ClientCallbackMessage
    | ClientMountMessage
    | ClientNavigateMessage
    | ClientUnmountMessage
    | ClientApiResultMessage
)
