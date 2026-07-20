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
	stack: string;
	phase:
		| "render"
		| "callback"
		| "mount"
		| "unmount"
		| "navigate"
		| "server"
		| "effect"
		| "connect";
	details: Record<string, any>;
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

export interface ServerChannelEventMessage {
	type: "channel_event";
	channel: string;
	event: string;
	payload: any;
}

export interface ServerChannelRequestMessage {
	type: "channel_request";
	channel: string;
	event: string;
	requestId: string;
	payload: any;
}

export interface ServerChannelSuccessMessage {
	type: "channel_response";
	channel: string;
	responseTo: string;
	ok: true;
	payload: any;
}

export interface ServerChannelErrorMessage {
	type: "channel_response";
	channel: string;
	responseTo: string;
	ok: false;
	error: string;
}

export type ServerChannelResponseMessage =
	| ServerChannelSuccessMessage
	| ServerChannelErrorMessage;
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
	| ServerChannelEventMessage
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
	type: "channel_event";
	channel: string;
	event: string;
	payload: any;
}

export interface ClientChannelRequestMessage {
	type: "channel_request";
	channel: string;
	event: string;
	requestId: string;
	payload: any;
}

export interface ClientChannelSuccessMessage {
	type: "channel_response";
	channel: string;
	responseTo: string;
	ok: true;
	payload: any;
}

export interface ClientChannelErrorMessage {
	type: "channel_response";
	channel: string;
	responseTo: string;
	ok: false;
	error: string;
}

export type ClientChannelResponseMessage =
	| ClientChannelSuccessMessage
	| ClientChannelErrorMessage;
export type ClientChannelMessage =
	| ClientChannelEventMessage
	| ClientChannelRequestMessage
	| ClientChannelResponseMessage;

export interface ClientJsResultSuccessMessage {
	type: "js_result";
	id: string;
	ok: true;
	result: any;
}

export interface ClientJsResultErrorMessage {
	type: "js_result";
	id: string;
	ok: false;
	error: string;
}

export type ClientJsResultMessage =
	| ClientJsResultSuccessMessage
	| ClientJsResultErrorMessage;

export type ClientMessage =
	| ClientAttachMessage
	| ClientCallbackMessage
	| ClientUpdateMessage
	| ClientDetachMessage
	| ClientApiResultMessage
	| ClientChannelEventMessage
	| ClientChannelRequestMessage
	| ClientChannelResponseMessage
	| ClientJsResultMessage;
