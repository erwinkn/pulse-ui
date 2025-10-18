// Public API surface for pulse-client

// Core React bindings
export { PulseProvider, usePulseClient, PulseView } from "./pulse";
export type { PulseConfig, PulseProviderProps, PulsePrerender } from "./pulse";
export { usePulseChannel } from "./usePulseChannel";
export { PulseChannelResetError } from "./channel";
export type { ChannelBridge } from "./channel";

// Client implementation (types only - implementation is internal)
export type {
  PulseClient,
  MountedView,
  ConnectionStatusListener,
  ServerErrorListener,
} from "./client";

// VDOM types and helpers
export type {
  VDOM,
  VDOMNode,
  VDOMElement,
  VDOMUpdate,
  ComponentRegistry,
} from "./vdom";

// Renderer helpers (implementation is internal)
export {
  applyUpdates as applyReactTreeUpdates,
  RenderLazy,
} from "./renderer";

// Form helpers
export { PulseForm, submitForm } from "./form";
export type { PulseFormProps } from "./form";

// Messages (types only)
export type {
  ServerMessage,
  ServerInitMessage,
  ServerUpdateMessage,
  ServerErrorMessage,
  ServerErrorInfo,
  ServerApiCallMessage,
  ServerNavigateToMessage,
  ServerChannelRequestMessage,
  ServerChannelResponseMessage,
  ServerChannelMessage,
  ClientMessage,
  ClientCallbackMessage,
  ClientMountMessage,
  ClientNavigateMessage,
  ClientUnmountMessage,
  ClientApiResultMessage,
  ClientChannelRequestMessage,
  ClientChannelResponseMessage,
  ClientChannelMessage,
} from "./messages";

// Transports (types only - implementation is internal)
export type { Transport, MessageListener } from "./transport";

// Server helpers
export { extractServerRouteInfo } from "./helpers";
export type { RouteInfo } from "./helpers";

// Serialization helpers
export { extractEvent } from "./serialize/events";
export {
  encodeForWire,
  decodeFromWire,
  cleanForSerialization,
} from "./serialize/clean";
export {
  serialize as serialize,
  deserialize as deserialize,
} from "./serialize/serializer";
