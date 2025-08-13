// Public API surface for pulse-client

// Core React bindings
export {
  PulseProvider,
  usePulseClient,
  PulseView,
  usePulseRenderHelpers,
} from "./pulse";
export type { PulseConfig, PulseProviderProps } from "./pulse";

// Client implementation
export { PulseSocketIOClient } from "./client";
export type {
  PulseClient,
  MountedView,
  VDOMListener,
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
  createElementNode,
  createFragment,
  createMountPoint,
  applyVDOMUpdates,
} from "./renderer";

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
export { extractEvent } from "./serialize";
