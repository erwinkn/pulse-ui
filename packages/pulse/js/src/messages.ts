// =================================================================
// Message Types
// =================================================================

import type { RouteInfo } from "./helpers";
import type { VDOM, VDOMNode, VDOMUpdate } from "./vdom";

// Based on pulse/messages.py. All view-scoped messages carry the unique id of
// the owning view (`view`).
export interface ServerInitMessage {
	type: "vdom_init";
	view: string;
	// Route pattern path (e.g. "/users/:id"), used to associate the view with
	// its generated route module.
	routePath: string;
	vdom: VDOM;
}

export interface ServerUpdateMessage {
	type: "vdom_update";
	view: string;
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
	// Omitted for session-level errors that are not tied to a view
	view?: string;
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
	view?: string;
	channel: string;
	event: string;
	payload?: any;
	requestId?: string;
	responseTo?: never;
	error?: any;
}

export interface ServerChannelResponseMessage {
	type: "channel_message";
	view?: string;
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
	sourceView?: string;
	sourcePathname?: string;
}

export interface ServerReloadMessage {
	type: "reload";
}

export interface ServerResumeView {
	view: string;
	attachId?: string;
}

export interface ServerResumeChannel {
	channel: string;
	view: string;
}

export interface ServerResumeMessage {
	type: "server_resume";
	resumeId: string;
	status: "ok" | "reload";
	views?: ServerResumeView[];
	channels?: ServerResumeChannel[];
}

export interface ServerNavigateResultMessage {
	type: "navigate_result";
	nav: string;
	status: "ok" | "redirect" | "notFound" | "error";
	redirect?: string;
	// Route pattern path -> fresh init message, or null to keep the live view
	views?: Record<string, ServerInitMessage | null>;
}

export interface ServerAttachAckMessage {
	type: "attach_ack";
	view: string;
	attachId: string;
}

export interface ServerJsExecMessage {
	type: "js_exec";
	view: string;
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
	| ServerResumeMessage
	| ServerNavigateResultMessage
	| ServerAttachAckMessage
	| ServerChannelRequestMessage
	| ServerChannelResponseMessage
	| ServerJsExecMessage;

export interface ClientCallbackMessage {
	type: "callback";
	view: string;
	callback: string;
	args: any[];
}

export interface ClientAttachMessage {
	type: "attach";
	view: string;
	routeInfo: RouteInfo;
	attachId: string;
}
export interface ClientUpdateMessage {
	type: "update";
	view: string;
	routeInfo: RouteInfo;
}
export interface ClientDetachMessage {
	type: "detach";
	view: string;
}

export interface ClientNavigateMessage {
	type: "navigate";
	nav: string;
	routeInfo: RouteInfo;
	prefetch?: boolean;
}

export interface ClientResumeView {
	view: string;
	routeInfo: RouteInfo;
	attachId?: string;
}

export interface ClientResumeChannel {
	channel: string;
	view: string;
}

export interface ClientResumeMessage {
	type: "client_resume";
	resumeId: string;
	views: ClientResumeView[];
	channels: ClientResumeChannel[];
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

export interface ClientChannelConnectMessage {
	type: "channel_connect";
	channel: string;
	view: string;
}

export interface ClientChannelDisconnectMessage {
	type: "channel_disconnect";
	channel: string;
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
	| ClientNavigateMessage
	| ClientResumeMessage
	| ClientApiResultMessage
	| ClientChannelRequestMessage
	| ClientChannelResponseMessage
	| ClientChannelConnectMessage
	| ClientChannelDisconnectMessage
	| ClientJsResultMessage;
