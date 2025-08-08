from typing import Any, TypedDict, Literal

from pulse.diff import VDOMOperation
from pulse.vdom import VDOM


# ====================
# Helpers
# ====================
class RouteInfo(TypedDict):
    pathname: str
    hash: str
    query: str
    queryParams: dict[str, str]
    pathParams: dict[str, str]
    catchall: list[str]


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


ServerMessage = ServerInitMessage | ServerUpdateMessage | ServerErrorMessage


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
    currentVDOM: VDOM


class ClientNavigateMessage(TypedDict):
    type: Literal["navigate"]
    path: str
    routeInfo: RouteInfo


class ClientUnmountMessage(TypedDict):
    type: Literal["unmount"]
    path: str


ClientMessage = (
    ClientCallbackMessage
    | ClientMountMessage
    | ClientNavigateMessage
    | ClientUnmountMessage
)
