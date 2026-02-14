// =================================================================
// Message Types
// =================================================================

import type { RouteInfo } from "./helpers";
import type { VDOM, VDOMNode, VDOMUpdate } from "./vdom";

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

export type ErrorCode =
	| "render"
	| "render.loop"
	| "callback"
	| "navigate"
	| "ref.mount"
	| "ref.unmount"
	| "timer.later"
	| "timer.repeat"
	| "channel"
	| "form"
	| "api"
	| "middleware.prerender"
	| "middleware.connect"
	| "middleware.message"
	| "middleware.channel"
	| "setup"
	| "init"
	| "plugin.startup"
	| "plugin.setup"
	| "plugin.shutdown"
	| "query.handler"
	| "mutation.handler"
	| "system";

export interface ServerError {
	message: string;
	stack?: string;
	code: ErrorCode;
	details?: Record<string, any>;
}

export interface ServerErrorMessage {
	type: "server_error";
	path?: string;
	error: ServerError;
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

export interface ServerChannelRequestMessage {
	type: "channel_message";
	channel: string;
	event: string;
	payload?: any;
	requestId?: string;
	responseTo?: never;
	error?: any;
}

export interface ServerChannelResponseMessage {
	type: "channel_message";
	channel: string;
	event?: undefined;
	responseTo: string;
	payload?: any;
	error?: any;
	requestId?: never;
}

export type ServerChannelMessage = ServerChannelRequestMessage | ServerChannelResponseMessage;

export interface ServerNavigateToMessage {
	type: "navigate_to";
	path: string;
	replace: boolean;
	hard: boolean;
}

export interface ServerReloadMessage {
	type: "reload";
}

export interface ServerJsExecMessage {
	type: "js_exec";
	path: string;
	id: string;
	expr: VDOMNode;
}

export type ServerMessage =
	| ServerInitMessage
	| ServerUpdateMessage
	| ServerErrorMessage
	| ServerApiCallMessage
	| ServerNavigateToMessage
	| ServerReloadMessage
	| ServerChannelRequestMessage
	| ServerChannelResponseMessage
	| ServerJsExecMessage;

export interface ClientCallbackMessage {
	type: "callback";
	path: string;
	callback: string;
	args: any[];
}

export interface ClientAttachMessage {
	type: "attach";
	path: string;
	routeInfo: RouteInfo;
}
export interface ClientUpdateMessage {
	type: "update";
	path: string;
	routeInfo: RouteInfo;
}
export interface ClientDetachMessage {
	type: "detach";
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

export interface ClientChannelRequestMessage {
	type: "channel_message";
	channel: string;
	event: string;
	payload?: any;
	requestId?: string;
	responseTo?: never;
	error?: any;
}

export interface ClientChannelResponseMessage {
	type: "channel_message";
	channel: string;
	event?: undefined;
	responseTo: string;
	payload?: any;
	error?: any;
	requestId?: never;
}

export type ClientChannelMessage = ClientChannelRequestMessage | ClientChannelResponseMessage;

export interface ClientJsResultMessage {
	type: "js_result";
	id: string;
	result: any;
	error: string | null;
}

export type ClientMessage =
	| ClientAttachMessage
	| ClientCallbackMessage
	| ClientUpdateMessage
	| ClientDetachMessage
	| ClientApiResultMessage
	| ClientChannelRequestMessage
	| ClientChannelResponseMessage
	| ClientJsResultMessage;
