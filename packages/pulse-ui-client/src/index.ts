// Public API surface for pulse-client

// Core React bindings
export { PulseProvider, usePulseClient, PulseView } from "./pulse";
export type { PulseConfig, PulseProviderProps, PulsePrerender } from "./pulse";

// Client implementation
export { PulseSocketIOClient } from "./client";
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

// Renderer helpers
export {
  VDOMRenderer,
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
  ClientMessage,
  ClientCallbackMessage,
  ClientMountMessage,
  ClientNavigateMessage,
  ClientUnmountMessage,
  ClientApiResultMessage,
} from "./messages";

// Transports
export { SocketIOTransport } from "./transport";
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
export { serialize, deserialize } from "./serialize/v3"
