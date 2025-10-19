// Public API surface for pulse-client

export type { ChannelBridge } from "./channel";
export { PulseChannelResetError } from "./channel";
export type {
	ConnectionStatusListener,
	MountedView,
	PulseClient,
	ServerErrorListener,
} from "./client";
// Client implementation
export { PulseSocketIOClient } from "./client";
export type { PulseFormProps } from "./form";
// Form helpers
export { PulseForm, submitForm } from "./form";
export type { RouteInfo } from "./helpers";
// Server helpers
export { extractServerRouteInfo } from "./helpers";
// Messages (types only)
export type {
	ClientApiResultMessage,
	ClientCallbackMessage,
	ClientChannelMessage,
	ClientChannelRequestMessage,
	ClientChannelResponseMessage,
	ClientMessage,
	ClientMountMessage,
	ClientNavigateMessage,
	ClientUnmountMessage,
	ServerApiCallMessage,
	ServerChannelMessage,
	ServerChannelRequestMessage,
	ServerChannelResponseMessage,
	ServerErrorInfo,
	ServerErrorMessage,
	ServerInitMessage,
	ServerMessage,
	ServerNavigateToMessage,
	ServerUpdateMessage,
} from "./messages";
export type { PulseConfig, PulsePrerender, PulseProviderProps } from "./pulse";
// Core React bindings
export { PulseProvider, PulseView, usePulseClient } from "./pulse";
// Renderer helpers
export {
	applyUpdates as applyReactTreeUpdates,
	RenderLazy,
	VDOMRenderer,
} from "./renderer";
export {
	cleanForSerialization,
	decodeFromWire,
	encodeForWire,
} from "./serialize/clean";
// Serialization helpers
export { extractEvent } from "./serialize/events";
export {
	deserialize,
	serialize,
} from "./serialize/serializer";
export type { MessageListener, Transport } from "./transport";
// Transports
export { SocketIOTransport } from "./transport";
export { usePulseChannel } from "./usePulseChannel";
// VDOM types and helpers
export type {
	ComponentRegistry,
	VDOM,
	VDOMElement,
	VDOMNode,
	VDOMUpdate,
} from "./vdom";
