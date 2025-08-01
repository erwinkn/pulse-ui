from typing import Any, TypedDict, Literal

from pulse.diff import VDOMOperation
from pulse.vdom import VDOMNode


class ServerInitMessage(TypedDict):
    type: Literal["vdom_init"]
    vdom: VDOMNode


class ServerUpdateMessage(TypedDict):
    type: Literal["vdom_update"]
    ops: list[VDOMOperation]


ServerMessage = ServerInitMessage | ServerUpdateMessage


class ClientCallbackMessage(TypedDict):
    type: Literal["callback"]
    callback: str
    args: list[Any]


class ClientNavigateMessage(TypedDict):
    type: Literal["navigate"]
    route: str


ClientMessage = ClientCallbackMessage | ClientNavigateMessage
