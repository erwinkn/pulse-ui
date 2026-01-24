// Public API surface for pulse-client

export type { ChannelBridge } from "./channel";
export { PulseChannelResetError, usePulseChannel } from "./channel";
// Client implementation (types only - implementation is internal)
export type {
	ConnectionStatusListener,
	MountedView,
	PulseClient,
} from "./client";
export type { PulseFormProps } from "./form";
// Form helpers
export { PulseForm, submitForm } from "./form";
export type { LocationLike, RouteInfo } from "./helpers";
// Route helpers
export { buildRouteInfo } from "./helpers";
// Messages (types only)
export type {
	ClientApiResultMessage,
	ClientAttachMessage,
	ClientCallbackMessage,
	ClientChannelMessage,
	ClientChannelRequestMessage,
	ClientChannelResponseMessage,
	ClientDetachMessage,
	ClientMessage,
	ClientUpdateMessage,
	ServerApiCallMessage,
	ServerChannelMessage,
	ServerChannelRequestMessage,
	ServerChannelResponseMessage,
	ServerError,
	ServerErrorMessage,
	ServerInitMessage,
	ServerMessage,
	ServerNavigateToMessage,
	ServerUpdateMessage,
} from "./messages";
export type { PulseConfig, PulsePrerender, PulseProviderProps } from "./pulse";
// Core React bindings
export { PulseProvider, PulseView, usePulseClient } from "./pulse";
// Router
export type {
	MatchResult,
	NavigateFunction,
	NavigateOptions,
	PulseRoute,
	RouteLoader,
	RouteLoaderMap,
	RouteModule,
} from "./router";
export {
	Link,
	Outlet,
	PulseRouterProvider,
	PulseRoutes,
	matchRoutes,
	preloadRoutesForPath,
	prefetchRouteModules,
	useLocation,
	useNavigate,
	useParams,
	useRouteInfo,
	useRouter,
} from "./router";
// Renderer helpers
// Renderer (structural expressions + eval-keyed props)
export { VDOMRenderer } from "./renderer";
// Serialization helpers
// export { extractEvent } from "./serialize/events";
// export {
//   encodeForWire,
//   decodeFromWire,
//   cleanForSerialization,
// } from "./serialize/clean";
export { deserialize, serialize } from "./serialize/serializer";
// Transports (types only - implementation is internal)
export type { MessageListener, Transport } from "./transport";
// VDOM types and helpers
export type {
	ComponentRegistry,
	ComponentRegistry as ComponentRegistry2,
	VDOM,
	VDOMElement,
	VDOMExpr,
	VDOMNode,
	VDOMPropValue,
	VDOMUpdate,
} from "./vdom";
