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

export interface ServerError {
	message: string;
	stack?: string;
	phase:
		| "render"
		| "callback"
		| "mount"
		| "unmount"
		| "navigate"
		| "server"
		| "effect"
		| "connect"
		| "channel";
	details?: Record<string, any>;
}

export interface ServerErrorMessage {
	type: "server_error";
	path: string;
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

export type ChannelErrorCode = "no_handler" | "denied" | "handler_error";

export interface ChannelError {
	code: ChannelErrorCode;
	message: string;
}

export interface ServerChannelEventMessage {
	type: "channel";
	action: "event";
	channel: string;
	event: string;
	payload?: any;
}

export interface ServerChannelRequestMessage {
	type: "channel";
	action: "request";
	channel: string;
	event: string;
	requestId: string;
	payload?: any;
}

export interface ServerChannelResponseMessage {
	type: "channel";
	action: "response";
	channel: string;
	responseTo: string;
	payload?: any;
	error?: ChannelError;
}

export type ServerChannelMessage =
	| ServerChannelEventMessage
	| ServerChannelRequestMessage
	| ServerChannelResponseMessage;

export interface ServerNavigateToMessage {
	type: "navigate_to";
	path: string;
	replace: boolean;
	hard: boolean;
	sourceRoutePath?: string;
	sourcePath?: string;
	sourceMountId?: string;
}

export interface ServerReloadMessage {
	type: "reload";
}

export interface ServerAttachAckMessage {
	type: "attach_ack";
	path: string;
	attachId: string;
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
	| ServerAttachAckMessage
	| ServerChannelMessage
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
	attachId: string;
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

export interface ClientChannelEventMessage {
	type: "channel";
	action: "event";
	channel: string;
	event: string;
	payload?: any;
}

export interface ClientChannelRequestMessage {
	type: "channel";
	action: "request";
	channel: string;
	event: string;
	requestId: string;
	payload?: any;
}

export interface ClientChannelResponseMessage {
	type: "channel";
	action: "response";
	channel: string;
	responseTo: string;
	payload?: any;
	error?: ChannelError;
}

export type ClientChannelMessage =
	| ClientChannelEventMessage
	| ClientChannelRequestMessage
	| ClientChannelResponseMessage;

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
	| ClientChannelMessage
	| ClientJsResultMessage;
