// =================================================================
// Message Types
// =================================================================

import type { RouteInfo } from "./helpers";
import type { VDOM, VDOMNode, VDOMUpdate } from "./vdom";

// Based on pulse/messages.py
export interface ViewSnapshot {
	viewId: string;
	revision: number;
	vdom: VDOM;
}

export interface ServerUpdateMessage {
	type: "vdom_update";
	path: string;
	viewId: string;
	baseRevision: number;
	revision: number;
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
	viewId?: string;
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
	origin?: {
		viewId: string;
		pathname: string;
	};
}

export interface ServerReloadMessage {
	type: "reload";
}

export interface ServerAttachAckMessage {
	type: "attach_ack";
	path: string;
	attachId: string;
	viewId: string;
	revision: number;
	snapshot?: ViewSnapshot;
}

export interface ServerResyncViewMessage {
	type: "resync_view";
	path: string;
	viewId: string;
}

export interface ServerJsExecMessage {
	type: "js_exec";
	path: string;
	viewId: string;
	id: string;
	expr: VDOMNode;
}

export type ServerMessage =
	| ServerUpdateMessage
	| ServerErrorMessage
	| ServerApiCallMessage
	| ServerNavigateToMessage
	| ServerReloadMessage
	| ServerAttachAckMessage
	| ServerResyncViewMessage
	| ServerChannelRequestMessage
	| ServerChannelResponseMessage
	| ServerJsExecMessage;

export interface ClientCallbackMessage {
	type: "callback";
	path: string;
	viewId: string;
	revision: number;
	callback: string;
	args: any[];
}

export interface ClientAttachMessage {
	type: "attach";
	path: string;
	routeInfo: RouteInfo;
	attachId: string;
	viewId: string;
	revision: number;
	instanceId: string;
}
export interface ClientUpdateMessage {
	type: "update";
	path: string;
	viewId: string;
	revision: number;
	routeInfo: RouteInfo;
}
export interface ClientDetachMessage {
	type: "detach";
	path: string;
	viewId: string;
	instanceId: string;
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
	viewId: string;
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
