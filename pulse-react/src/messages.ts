// =================================================================
// Message Types
// =================================================================

import type { VDOM, VDOMUpdate } from "./vdom";
import type { RouteInfo } from "./helpers";

// Based on pulse/messages.py
export interface ServerInitMessage {
  type: "vdom_init";
  path: string;
  vdom: VDOM;
}

export interface ServerUpdateMessage {
  type: "vdom_update";
  path: string;
  ops: VDOMUpdate[];
}

export interface ServerErrorInfo {
  message: string;
  stack?: string;
  phase: "render" | "callback" | "mount" | "unmount" | "navigate" | "server";
  details?: Record<string, any>;
}

export interface ServerErrorMessage {
  type: "server_error";
  path: string;
  error: ServerErrorInfo;
}

export interface ServerApiCallMessage {
  type: "api_call";
  id: string;
  url: string; // absolute or relative
  method: string;
  headers: Record<string, string>;
  body: any | null;
  credentials: "include" | "omit";
}

export interface ServerNavigateToMessage {
  type: "navigate_to";
  path: string;
}

export type ServerMessage =
  | ServerInitMessage
  | ServerUpdateMessage
  | ServerErrorMessage
  | ServerApiCallMessage
  | ServerNavigateToMessage;

export interface ClientCallbackMessage {
  type: "callback";
  path: string;
  callback: string;
  args: any[];
}

export interface ClientMountMessage {
  type: "mount";
  path: string;
  routeInfo: RouteInfo;
}
export interface ClientNavigateMessage {
  type: "navigate";
  path: string;
  routeInfo: RouteInfo;
}
export interface ClientUnmountMessage {
  type: "unmount";
  path: string;
}

export interface ClientApiResultMessage {
  type: "api_result";
  id: string;
  ok: boolean;
  status: number;
  headers: Record<string, string>;
  body: any | null;
}

export type ClientMessage =
  | ClientMountMessage
  | ClientCallbackMessage
  | ClientNavigateMessage
  | ClientUnmountMessage
  | ClientApiResultMessage;
