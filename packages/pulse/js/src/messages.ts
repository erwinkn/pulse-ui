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

export interface ChannelMessageBase {
	type: "channel";
	channel: string;
}

export interface ChannelConnectMessage extends ChannelMessageBase {
	action: "connect";
	subscriptionId: string;
	owner?: string;
}

export interface ChannelDisconnectMessage extends ChannelMessageBase {
	action: "disconnect";
	subscriptionId: string;
	owner?: string;
}

export interface ChannelConnectAckMessage extends ChannelMessageBase {
	action: "connect_ack";
	subscriptionId: string;
	accepted: boolean;
	error?: string;
}

export interface ChannelCloseMessage extends ChannelMessageBase {
	action: "close";
	subscriptionId: string;
	reason?: string;
}

export interface ChannelEventMessage extends ChannelMessageBase {
	action: "event";
	event: string;
	payload?: any;
	subscriptionId?: string;
}

export interface ChannelRequestMessage extends ChannelMessageBase {
	action: "request";
	event: string;
	requestId: string;
	payload?: any;
	subscriptionId?: string;
}

export interface ChannelResponseMessage extends ChannelMessageBase {
	action: "response";
	responseTo: string;
	payload?: any;
	error?: any;
	subscriptionId?: string;
}

export type ClientChannelMessage =
	| ChannelConnectMessage
	| ChannelDisconnectMessage
	| ChannelEventMessage
	| ChannelRequestMessage
	| ChannelResponseMessage;

export type ServerChannelMessage =
	| ChannelConnectAckMessage
	| ChannelCloseMessage
	| ChannelEventMessage
	| ChannelRequestMessage
	| ChannelResponseMessage;

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
