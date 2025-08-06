import type { VDOM, VDOMNode } from "./vdom";
import { applyVDOMUpdates } from "./renderer";
import { extractEvent } from "./serialize";
import type {
  ClientCallbackMessage,
  ClientMountMessage,
  ClientNavigateMessage,
  RouteInfo,
} from "./messages";

import type { ServerMessage, ClientMessage } from "./messages";
import { io, Socket } from "socket.io-client";

export interface MountedView {
  vdom: VDOM;
  listener: VDOMListener;
  routeInfo: RouteInfo;
}

export type VDOMListener = (node: VDOMNode) => void;
export type ConnectionStatusListener = (connected: boolean) => void;

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

  constructor(private url: string) {
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
            path,
            routeInfo: route.routeInfo,
            currentVDOM: route.vdom,
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
    this.sendMessage({
      type: "mount",
      currentVDOM: view.vdom,
      path,
      routeInfo: view.routeInfo,
    });
    return () => {
      this.activeViews.delete(path);
    };
  }

  public async navigate(path: string, routeInfo: RouteInfo) {
    const route = this.activeViews.get(path)!;
    await this.sendMessage({
      type: "navigate",
      path,
      routeInfo,
    });
  }

  public async leave(path: string) {
    await this.sendMessage({ type: "unmount", path });
  }

  public disconnect() {
    this.socket?.disconnect();
    this.socket = null;
    this.messageQueue = [];
    this.connectionListeners.clear();
    this.activeViews.clear();
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
        break;
      }
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
