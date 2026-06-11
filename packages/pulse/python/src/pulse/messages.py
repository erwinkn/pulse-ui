from typing import Any, Literal, NotRequired, TypedDict

from pulse.routing import RouteInfo
from pulse.transpiler.vdom import VDOM, VDOMNode, VDOMOperation


# ====================
# Server messages
# ====================
class ServerInitMessage(TypedDict):
	type: Literal["vdom_init"]
	# Unique id of the view this VDOM belongs to
	view: str
	# Route pattern path (e.g. "/users/:id"), used by the client to associate
	# the view with its generated route module.
	routePath: str
	vdom: VDOM


class ServerUpdateMessage(TypedDict):
	type: Literal["vdom_update"]
	view: str
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
	# Omitted for session-level errors that are not tied to a view
	view: NotRequired[str]
	error: ServerErrorInfo


class ServerNavigateToMessage(TypedDict):
	type: Literal["navigate_to"]
	path: str
	replace: bool
	hard: bool
	# Origin view id + pathname captured when the navigation was requested.
	# Route-bound navigations are dropped when the origin view is gone or its
	# URL has changed since.
	sourceView: NotRequired[str]
	sourcePathname: NotRequired[str]


class ServerReloadMessage(TypedDict):
	type: Literal["reload"]


class ServerResumeView(TypedDict):
	view: str
	attachId: NotRequired[str]


class ServerResumeChannel(TypedDict):
	channel: str
	view: str


class ServerResumeMessage(TypedDict):
	type: Literal["server_resume"]
	resumeId: str
	status: Literal["ok", "reload"]
	views: NotRequired[list[ServerResumeView]]
	channels: NotRequired[list[ServerResumeChannel]]


class ServerNavigateResultMessage(TypedDict):
	"""Reply to a client navigate/prefetch request.

	`views` maps each matched route pattern path to its freshly rendered init
	message, or None when the client should keep using its live view for that
	pattern (state persists across navigation).
	"""

	type: Literal["navigate_result"]
	nav: str
	status: Literal["ok", "redirect", "notFound", "error"]
	redirect: NotRequired[str]
	views: NotRequired[dict[str, "ServerInitMessage | None"]]


class ServerAttachAckMessage(TypedDict):
	type: Literal["attach_ack"]
	view: str
	attachId: str


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
	view: NotRequired[str]
	channel: str
	event: str
	payload: Any
	requestId: NotRequired[str]
	error: NotRequired[Any]


class ServerChannelResponseMessage(TypedDict):
	type: Literal["channel_message"]
	view: NotRequired[str]
	channel: str
	event: None
	responseTo: str
	payload: Any
	error: NotRequired[Any]


class ServerJsExecMessage(TypedDict):
	"""Execute JavaScript expression on the client."""

	type: Literal["js_exec"]
	view: str
	id: str
	expr: VDOMNode


# ====================
# Client messages
# ====================
class ClientCallbackMessage(TypedDict):
	type: Literal["callback"]
	view: str
	callback: str
	args: list[Any]


class ClientAttachMessage(TypedDict):
	type: Literal["attach"]
	view: str
	routeInfo: RouteInfo
	attachId: NotRequired[str]


class ClientUpdateMessage(TypedDict):
	type: Literal["update"]
	view: str
	routeInfo: RouteInfo


class ClientDetachMessage(TypedDict):
	type: Literal["detach"]
	view: str


class ClientNavigateMessage(TypedDict):
	"""Client-side navigation (or hover prefetch) over the socket.

	The server re-matches `routeInfo.pathname` against the route tree (Python
	is the source of truth), renders views for route patterns the session does
	not have live yet, and replies with a navigate_result correlated by `nav`.
	Prefetch requests render upcoming views without disturbing live ones.
	"""

	type: Literal["navigate"]
	nav: str
	routeInfo: RouteInfo
	prefetch: NotRequired[bool]


class ClientResumeView(TypedDict):
	view: str
	routeInfo: RouteInfo
	attachId: NotRequired[str]


class ClientResumeChannel(TypedDict):
	channel: str
	view: str


class ClientResumeMessage(TypedDict):
	type: Literal["client_resume"]
	resumeId: str
	views: list[ClientResumeView]
	channels: list[ClientResumeChannel]


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


class ClientChannelConnectMessage(TypedDict):
	type: Literal["channel_connect"]
	channel: str
	view: str


class ClientChannelDisconnectMessage(TypedDict):
	type: Literal["channel_disconnect"]
	channel: str


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
	| ServerReloadMessage
	| ServerResumeMessage
	| ServerNavigateResultMessage
	| ServerAttachAckMessage
	| ServerChannelMessage
	| ServerJsExecMessage
)


ClientPulseMessage = (
	ClientCallbackMessage
	| ClientAttachMessage
	| ClientUpdateMessage
	| ClientDetachMessage
	| ClientNavigateMessage
	| ClientResumeMessage
	| ClientApiResultMessage
	| ClientJsResultMessage
)
ClientChannelMessage = (
	ClientChannelRequestMessage
	| ClientChannelResponseMessage
	| ClientChannelConnectMessage
	| ClientChannelDisconnectMessage
)
ClientMessage = ClientPulseMessage | ClientChannelMessage


class PrerenderPayload(TypedDict):
	paths: list[str]
	routeInfo: RouteInfo
	ttlSeconds: NotRequired[float | int]
	renderId: NotRequired[str]


class SocketIODirectives(TypedDict):
	headers: dict[str, str]
	auth: dict[str, str]
	query: dict[str, str]


class Directives(TypedDict):
	headers: dict[str, str]
	query: dict[str, str]
	socketio: SocketIODirectives


class Prerender(TypedDict):
	views: dict[str, ServerInitMessage | ServerNavigateToMessage | None]
	directives: Directives
