// Public API surface for pulse-client

export type { ChannelBridge } from "./channel";
export { PulseChannelResetError } from "./channel";
// Client implementation (types only - implementation is internal)
export type {
	ConnectionStatusListener,
	MountedView,
	PulseClient,
} from "./client";
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
// Renderer helpers
// Renderer (structural expressions + eval-keyed props)
export { RenderLazy, VDOMRenderer } from "./renderer";
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
export { usePulseChannel } from "./usePulseChannel";
// VDOM types and helpers
export type {
	ComponentRegistry,
	ComponentRegistry as ComponentRegistry2,
	VDOM,
	VDOM as VDOM2,
	VDOMElement,
	VDOMElement as VDOMElement2,
	VDOMExpr as VDOMExpr2,
	VDOMNode,
	VDOMNode as VDOMNode2,
	VDOMPropValue as VDOMPropValue2,
	VDOMUpdate,
	VDOMUpdate,
} from "./vdom";
