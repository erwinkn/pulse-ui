// Public API surface for pulse-client

export type { ChannelBridge } from "./channel";
export { PulseChannelResetError, usePulseChannel } from "./channel";
// Client implementation (types only - implementation is internal)
export type {
	ConnectionStatusListener,
	MountedView,
	PulseClient,
} from "./client";
export { PulseSocketIOClient } from "./client";
// Error handling
export type {
	DefaultErrorFallbackProps,
	ErrorBoundaryProps,
} from "./error-boundary";
export { DefaultErrorFallback, ErrorBoundary } from "./error-boundary";
export type { PulseFormProps } from "./form";
// Form helpers
export { PulseForm, submitForm } from "./form";
export type { RouteInfo } from "./helpers";
// Server helpers
export { extractServerRouteInfo } from "./helpers";
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
	ServerNavigationErrorMessage,
	ServerUpdateMessage,
} from "./messages";
export type { PulseConfig, PulsePrerender, PulseProviderProps } from "./pulse";
// Core React bindings
export { PulseProvider, PulseView, usePulseClient } from "./pulse";
// Renderer helpers
// Renderer (structural expressions + eval-keyed props)
export { VDOMRenderer } from "./renderer";
// Router - public API
export type {
	LinkProps,
	Location,
	MatchResult,
	NavigateFn,
	NavigateOptions,
	NavigationError,
	NavigationErrorContextValue,
	NavigationErrorProviderProps,
	NavigationProgressContextValue,
	NavigationProgressProps,
	NavigationProgressProviderProps,
	Params,
	PulseRouterContextValue,
	PulseRouterProviderProps,
	RouteMatch,
} from "./router";
export {
	compareRoutes,
	isExternalUrl,
	Link,
	matchPath,
	NavigationError,
	NavigationErrorProvider,
	NavigationProgress,
	NavigationProgressProvider,
	PulseRouterContext,
	PulseRouterProvider,
	scrollToHash,
	selectBestMatch,
	useHashScroll,
	useLocation,
	useNavigate,
	useNavigationError,
	useNavigationProgress,
	useParams,
	usePulseRouterContext,
} from "./router";
// Serialization helpers
// export { extractEvent } from "./serialize/events";
// export {
//   encodeForWire,
//   decodeFromWire,
//   cleanForSerialization,
// } from "./serialize/clean";
export { deserialize, serialize } from "./serialize/serializer";
// Server-side rendering
export type { RenderConfig } from "./server/render";
export { renderVdom } from "./server/render";
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
