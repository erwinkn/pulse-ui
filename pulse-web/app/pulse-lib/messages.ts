// =================================================================
// Message Types
// =================================================================

import type { LoaderFunctionArgs } from "react-router";
import type { VDOM, VDOMUpdate } from "./vdom";

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

export type ServerMessage =
  | ServerInitMessage
  | ServerUpdateMessage
  | ServerErrorMessage;

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
  currentVDOM: VDOM;
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

export type ClientMessage =
  | ClientMountMessage
  | ClientCallbackMessage
  | ClientNavigateMessage
  | ClientUnmountMessage;

// =================================================================
// Other Types
// =================================================================

export interface RouteInfo {
  pathname: string;
  hash: string;
  query: string;
  queryParams: Record<string, string>;
  pathParams: Record<string, string | undefined>;
  catchall: string[];
}

export function extractServerRouteInfo({
  params,
  request,
}: LoaderFunctionArgs) {
  const { "*": catchall = "", ...pathParams } = params;
  const parsedUrl = new URL(request.url);

  return {
    hash: parsedUrl.hash,
    pathname: parsedUrl.pathname,
    query: parsedUrl.search,
    queryParams: Object.fromEntries(parsedUrl.searchParams.entries()),
    pathParams,
    catchall: catchall.length > 1 ? catchall.split("/") : [],
  } satisfies RouteInfo;
}
