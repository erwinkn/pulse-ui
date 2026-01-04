from typing import Any, Literal, NotRequired, TypedDict

from pulse.routing import RouteInfo
from pulse.transpiler.vdom import VDOM, VDOMNode, VDOMOperation


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


ServerErrorPhase = Literal[
	"render", "callback", "mount", "unmount", "navigate", "server", "effect", "connect"
]


class ServerErrorInfo(TypedDict, total=False):
	# High-level human message
	message: str
	# Full stack trace string (server formatted)
	stack: str
	# Which phase failed
	phase: ServerErrorPhase
	# Optional extra details (callback key, etc.)
	details: dict[str, Any]


class ServerErrorMessage(TypedDict):
	type: Literal["server_error"]
	path: str
	error: ServerErrorInfo


class ServerNavigateToMessage(TypedDict):
	type: Literal["navigate_to"]
	path: str
	replace: bool
	hard: bool


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


class ServerChannelRequestMessage(TypedDict):
	type: Literal["channel_message"]
	channel: str
	event: str
	payload: Any
	requestId: NotRequired[str]
	error: NotRequired[Any]


class ServerChannelResponseMessage(TypedDict):
	type: Literal["channel_message"]
	channel: str
	event: None
	responseTo: str
	payload: Any
	error: NotRequired[Any]


class ServerJsExecMessage(TypedDict):
	"""Execute JavaScript expression on the client."""

	type: Literal["js_exec"]
	path: str
	id: str
	expr: VDOMNode


# ====================
# Client messages
# ====================
class ClientCallbackMessage(TypedDict):
	type: Literal["callback"]
	path: str
	callback: str
	args: list[Any]


class ClientAttachMessage(TypedDict):
	type: Literal["attach"]
	path: str
	routeInfo: RouteInfo


class ClientUpdateMessage(TypedDict):
	type: Literal["update"]
	path: str
	routeInfo: RouteInfo


class ClientDetachMessage(TypedDict):
	type: Literal["detach"]
	path: str


class ClientApiResultMessage(TypedDict):
	type: Literal["api_result"]
	id: str
	ok: bool
	status: int
	headers: dict[str, str]
	body: Any | None


class ClientChannelRequestMessage(TypedDict):
	type: Literal["channel_message"]
	channel: str
	event: str
	payload: Any
	requestId: NotRequired[str]
	error: NotRequired[Any]


class ClientChannelResponseMessage(TypedDict):
	type: Literal["channel_message"]
	channel: str
	event: None
	responseTo: str
	payload: Any
	error: NotRequired[Any]


class ClientJsResultMessage(TypedDict):
	"""Result of client-side JS execution."""

	type: Literal["js_result"]
	id: str
	result: Any
	error: str | None


ServerChannelMessage = ServerChannelRequestMessage | ServerChannelResponseMessage
ServerMessage = (
	ServerInitMessage
	| ServerUpdateMessage
	| ServerErrorMessage
	| ServerApiCallMessage
	| ServerNavigateToMessage
	| ServerChannelMessage
	| ServerJsExecMessage
)


ClientPulseMessage = (
	ClientCallbackMessage
	| ClientAttachMessage
	| ClientUpdateMessage
	| ClientDetachMessage
	| ClientApiResultMessage
	| ClientJsResultMessage
)
ClientChannelMessage = ClientChannelRequestMessage | ClientChannelResponseMessage
ClientMessage = ClientPulseMessage | ClientChannelMessage


class PrerenderPayload(TypedDict):
	paths: list[str]
	routeInfo: RouteInfo
	ttlSeconds: NotRequired[float | int]
	renderId: NotRequired[str]


class SocketIODirectives(TypedDict):
	headers: dict[str, str]
	auth: dict[str, str]


class Directives(TypedDict):
	headers: dict[str, str]
	socketio: SocketIODirectives


class Prerender(TypedDict):
	views: dict[str, ServerInitMessage | ServerNavigateToMessage | None]
	directives: Directives
