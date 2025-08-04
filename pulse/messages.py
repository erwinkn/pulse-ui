from typing import Any, TypedDict, Literal

from pulse.diff import VDOMOperation
from pulse.vdom import VDOMNode


class ServerInitMessage(TypedDict):
    type: Literal["vdom_init"]
    path: str
    vdom: VDOMNode


class ServerUpdateMessage(TypedDict):
    type: Literal["vdom_update"]
    path: str
    ops: list[VDOMOperation]


ServerMessage = ServerInitMessage | ServerUpdateMessage


class ClientCallbackMessage(TypedDict):
    type: Literal["callback"]
    path: str
    callback: str
    args: list[Any]


class ClientNavigateMessage(TypedDict):
    type: Literal["navigate"]
    path: str


class ClientLeaveMessage(TypedDict):
    type: Literal["leave"]
    path: str


ClientMessage = ClientCallbackMessage | ClientNavigateMessage | ClientLeaveMessage
