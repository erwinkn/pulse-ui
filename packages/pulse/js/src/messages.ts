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
	phase: "render" | "callback" | "mount" | "unmount" | "navigate" | "server";
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

export interface ServerChannelRequestMessage {
	type: "channel_message";
	channel: string;
	event: string;
	payload?: any;
	requestId?: string;
	error?: any;
}

export interface ReplyMessage {
	type: "reply";
	id: string;
	payload?: any;
	error?: any;
}

export type ServerChannelMessage = ServerChannelRequestMessage;

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
	| ServerChannelRequestMessage
	| ServerJsExecMessage
	| ReplyMessage;

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

export interface ClientChannelRequestMessage {
	type: "channel_message";
	channel: string;
	event: string;
	payload?: any;
	requestId?: string;
	error?: any;
}

export type ClientChannelMessage = ClientChannelRequestMessage;

export type ClientMessage =
	| ClientAttachMessage
	| ClientCallbackMessage
	| ClientUpdateMessage
	| ClientDetachMessage
	| ClientChannelRequestMessage
	| ReplyMessage;
