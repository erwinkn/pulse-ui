import type { RouteInfo } from "./helpers";
import type { ClientMountMessage } from "./messages";
import { applyVDOMUpdates } from "./renderer";
import { extractEvent } from "./serialize/events";
import type { VDOM, VDOMNode } from "./vdom";

import { io, Socket } from "socket.io-client";
import type {
  ClientApiResultMessage,
  ClientMessage,
  ServerApiCallMessage,
  ServerErrorInfo,
  ServerMessage,
} from "./messages";

export interface MountedView {
  vdom: VDOM;
  listener: VDOMListener;
  routeInfo: RouteInfo;
}

export type VDOMListener = (node: VDOMNode) => void;
export type ConnectionStatusListener = (connected: boolean) => void;
export type ServerErrorListener = (
  path: string,
  error: ServerErrorInfo | null
) => void;

export interface PulseClient {
  // Connection management
  connect(): Promise<void>;
  disconnect(): void;
  isConnected(): boolean;
  onConnectionChange(listener: ConnectionStatusListener): () => void;
  // Messages
  navigate(path: string, routeInfo: RouteInfo): Promise<void>;
  leave(path: string): Promise<void>;
  invokeCallback(path: string, callback: string, args: any[]): Promise<void>;
  // VDOM subscription
  mountView(path: string, view: MountedView): () => void;
}

export class PulseSocketIOClient {
  private activeViews: Map<string, MountedView>;
  private socket: Socket | null = null;
  private messageQueue: ClientMessage[];
  private connectionListeners: Set<ConnectionStatusListener> = new Set();
  private serverErrors: Map<string, ServerErrorInfo> = new Map();
  private serverErrorListeners: Set<ServerErrorListener> = new Set();

  constructor(
    private url: string,
    private frameworkNavigate?: (to: string) => void
  ) {
    this.socket = null;
    this.activeViews = new Map();
    this.messageQueue = [];
  }
  public isConnected(): boolean {
    return this.socket?.connected ?? false;
  }

  public async connect(): Promise<void> {
    if (this.socket) {
      return;
    }
    return new Promise((resolve, reject) => {
      const socket = io(this.url, {
        transports: ["websocket"],
      });
      this.socket = socket;

      socket.on("connect", () => {
        console.log("[SocketIOTransport] Connected:", this.socket?.id);
        // Make sure to send a navigate payload for all the routes
        for (const [path, route] of this.activeViews) {
          socket.emit("message", {
            type: "mount",
            path: path,
            routeInfo: route.routeInfo,
          } satisfies ClientMountMessage);
        }

        for (const payload of this.messageQueue) {
          // Already sent above
          if (payload.type === "mount" && this.activeViews.has(payload.path)) {
            continue;
          }
          // We're remounting all the routes, so no need to navigate
          if (payload.type === "navigate") {
            continue;
          }
          socket.emit("message", payload);
        }
        this.messageQueue = [];

        this.notifyConnectionListeners(true);
        resolve();
      });

      socket.on("connect_error", (err) => {
        console.error("[SocketIOTransport] Connection failed:", err);
        this.notifyConnectionListeners(false);
        reject(err);
      });

      socket.on("disconnect", () => {
        console.log("[SocketIOTransport] Disconnected");
        this.notifyConnectionListeners(false);
      });

      // Wrap in an arrow function to avoid losing the `this` reference
      socket.on("message", (data) => this.handleServerMessage(data));
    });
  }

  onConnectionChange(listener: ConnectionStatusListener): () => void {
    this.connectionListeners.add(listener);
    listener(this.isConnected());
    return () => {
      this.connectionListeners.delete(listener);
    };
  }

  private notifyConnectionListeners(connected: boolean): void {
    for (const listener of this.connectionListeners) {
      listener(connected);
    }
  }

  public onServerError(listener: ServerErrorListener): () => void {
    this.serverErrorListeners.add(listener);
    // Emit current errors to new listener
    for (const [path, err] of this.serverErrors) listener(path, err);
    return () => {
      this.serverErrorListeners.delete(listener);
    };
  }

  private notifyServerError(path: string, error: ServerErrorInfo | null) {
    for (const listener of this.serverErrorListeners) listener(path, error);
  }

  private async sendMessage(payload: ClientMessage): Promise<void> {
    if (this.isConnected()) {
      // console.log("[SocketIOTransport] Sending:", payload);
      this.socket!.emit("message", payload);
    } else {
      // console.log("[SocketIOTransport] Queuing message:", payload);
      this.messageQueue.push(payload);
    }
  }

  public mountView(path: string, view: MountedView) {
    if (this.activeViews.has(path)) {
      throw new Error(`Path ${path} is already mounted`);
    }
    this.activeViews.set(path, view);
    void this.sendMessage({
      type: "mount",
      path,
      routeInfo: view.routeInfo,
    });
  }

  public async navigate(path: string, routeInfo: RouteInfo) {
    await this.sendMessage({
      type: "navigate",
      path,
      routeInfo,
    });
  }

  public unmount(path: string) {
    void this.sendMessage({ type: "unmount", path });
    this.activeViews.delete(path);
  }

  public disconnect() {
    this.socket?.disconnect();
    this.socket = null;
    this.messageQueue = [];
    this.connectionListeners.clear();
    this.activeViews.clear();
    this.serverErrors.clear();
    this.serverErrorListeners.clear();
  }

  private handleServerMessage(message: ServerMessage) {
    // console.log("[PulseClient] Received message:", message);
    switch (message.type) {
      case "vdom_init": {
        const route = this.activeViews.get(message.path);
        if (route) {
          route.vdom = message.vdom;
          route.listener(route.vdom);
        }
        // Clear any prior error for this path on successful init
        if (this.serverErrors.has(message.path)) {
          this.serverErrors.delete(message.path);
          this.notifyServerError(message.path, null);
        }
        break;
      }
      case "vdom_update": {
        const route = this.activeViews.get(message.path);
        if (!route || !route.vdom) {
          console.error(
            `[PulseClient] Received VDOM update for path ${message.path} before initial tree was set.`
          );
          return;
        }
        route.vdom = applyVDOMUpdates(route.vdom, message.ops);
        route.listener(route.vdom);
        // Clear any prior error for this path on successful update
        if (this.serverErrors.has(message.path)) {
          this.serverErrors.delete(message.path);
          this.notifyServerError(message.path, null);
        }
        break;
      }
      case "server_error": {
        this.serverErrors.set(message.path, message.error);
        this.notifyServerError(message.path, message.error);
        break;
      }
      case "api_call": {
        void this.performApiCall(message);
        break;
      }
      case "navigate_to": {
        try {
          const dest = (message as any).path as string;
          if (this.frameworkNavigate) {
            this.frameworkNavigate(dest);
          } else {
            window.history.pushState({}, "", dest);
            window.dispatchEvent(new PopStateEvent("popstate"));
          }
        } catch (e) {
          console.error("Navigation error:", e);
        }
        break;
      }
    }
  }

  private async performApiCall(msg: ServerApiCallMessage) {
    try {
      const res = await fetch(msg.url, {
        method: msg.method || "GET",
        headers: {
          ...(msg.headers || {}),
          ...(msg.body != null && !("content-type" in (msg.headers || {}))
            ? { "content-type": "application/json" }
            : {}),
        },
        body:
          msg.body != null
            ? typeof msg.body === "string"
              ? msg.body
              : JSON.stringify(msg.body)
            : undefined,
        credentials: msg.credentials || "include",
      });
      const headersObj: Record<string, string> = {};
      res.headers.forEach((v, k) => (headersObj[k] = v));
      let body: any = null;
      const ct = res.headers.get("content-type") || "";
      if (ct.includes("application/json")) {
        body = await res.json().catch(() => null);
      } else {
        body = await res.text().catch(() => null);
      }
      const reply: ClientApiResultMessage = {
        type: "api_result",
        id: msg.id,
        ok: res.ok,
        status: res.status,
        headers: headersObj,
        body,
      };
      await this.sendMessage(reply);
    } catch (err) {
      const reply: ClientApiResultMessage = {
        type: "api_result",
        id: msg.id,
        ok: false,
        status: 0,
        headers: {},
        body: { error: String(err) },
      };
      await this.sendMessage(reply);
    }
  }

  public async invokeCallback(path: string, callback: string, args: any[]) {
    await this.sendMessage({
      type: "callback",
      path,
      callback,
      args: args.map(extractEvent),
    });
  }

  // public getVDOM(path: string): VDOM | null {
  //   return this.activeViews.get(path)?.vdom ?? null;
  // }
}
