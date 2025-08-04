from typing import Any, TypedDict, Literal

from pulse.diff import VDOMOperation
from pulse.vdom import VDOMNode


class ServerInitMessage(TypedDict):
    type: Literal["vdom_init"]
    route: str
    vdom: VDOMNode

class ServerUpdateMessage(TypedDict):
    type: Literal["vdom_update"]
    route: str
    ops: list[VDOMOperation]


ServerMessage = ServerInitMessage | ServerUpdateMessage


class ClientCallbackMessage(TypedDict):
    type: Literal["callback"]
    route: str
    callback: str
    args: list[Any]


class ClientNavigateMessage(TypedDict):
    type: Literal["navigate"]
    route: str

class ClientLeaveMesasge(TypedDict):
    type: Literal['leave']
    route: str


ClientMessage = ClientCallbackMessage | ClientNavigateMessage
