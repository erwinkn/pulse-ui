import { io, Socket } from "socket.io-client";
import type { VDOMNode, VDOMUpdate } from "./vdom";

// =================================================================
// Message Types
// =================================================================

// Based on pulse/messages.py
export interface ServerInitMessage {
  type: "vdom_init";
  path: string;
  vdom: VDOMNode;
}

export interface ServerUpdateMessage {
  type: "vdom_update";
  path: string;
  ops: VDOMUpdate[];
}

export type ServerMessage = ServerInitMessage | ServerUpdateMessage;

export interface ClientCallbackMessage {
  type: "callback";
  path: string;
  callback: string;
  args: any[];
}

export interface ClientNavigateMessage {
  type: "navigate";
  path: string;
}
export interface ClientLeaveMessage {
  type: "leave";
  path: string;
}

export type ClientMessage =
  | ClientCallbackMessage
  | ClientNavigateMessage
  | ClientLeaveMessage;

// =================================================================
// Transport Abstraction
// =================================================================

export type MessageListener = (message: ServerMessage) => void;
export type ConnectionStatusListener = (connected: boolean) => void;

export interface Transport {
  connect(listener: MessageListener): Promise<void>;
  disconnect(): void;
  sendMessage(payload: ClientMessage): Promise<void>;
  isConnected(): boolean;
  onConnectionChange(listener: ConnectionStatusListener): () => void;
}

// =================================================================
// Socket.IO Transport
// =================================================================

export class SocketIOTransport implements Transport {
  private socket: Socket | null = null;
  private listener: MessageListener | null = null;
  private messageQueue: ClientMessage[] = [];
  private connectionListeners: Set<ConnectionStatusListener> = new Set();

  constructor(private url: string) {}

  connect(listener: MessageListener): Promise<void> {
    this.listener = listener;
    return new Promise((resolve, reject) => {
      this.socket = io(this.url, {
        transports: ["websocket"],
      });

      this.socket.on("connect", () => {
        console.log("[SocketIOTransport] Connected:", this.socket?.id);

        for (const payload of this.messageQueue) {
          console.log("[SocketIOTransport] Sending queued message:", payload);
          this.socket?.emit("message", payload);
        }
        this.messageQueue = [];

        this.notifyConnectionListeners(true);
        resolve();
      });

      this.socket.on("connect_error", (err) => {
        console.error("[SocketIOTransport] Connection failed:", err);
        this.notifyConnectionListeners(false);
        reject(err);
      });

      this.socket.on("disconnect", () => {
        console.log("[SocketIOTransport] Disconnected");
        this.notifyConnectionListeners(false);
      });

      this.socket.on("message", (data: ServerMessage) => {
        console.log("[SocketIOTransport] Received message:", data);
        this.listener?.(data);
      });
    });
  }

  disconnect(): void {
    this.socket?.disconnect();
    this.socket = null;
    this.listener = null;
    this.messageQueue = [];
    this.connectionListeners.clear();
  }

  async sendMessage(payload: ClientMessage): Promise<void> {
    if (this.isConnected()) {
      console.log("[SocketIOTransport] Sending:", payload);
      this.socket!.emit("message", payload);
    } else {
      console.log("[SocketIOTransport] Queuing message:", payload);
      this.messageQueue.push(payload);
    }
  }

  isConnected(): boolean {
    return this.socket?.connected || false;
  }

  onConnectionChange(listener: ConnectionStatusListener): () => void {
    this.connectionListeners.add(listener);
    return () => {
      this.connectionListeners.delete(listener);
    };
  }

  private notifyConnectionListeners(connected: boolean): void {
    for (const listener of this.connectionListeners) {
      listener(connected);
    }
  }
}

// =================================================================
// In-Memory Transport (for testing)
// =================================================================

export class InMemoryTransport implements Transport {
  private listener: MessageListener | null = null;
  private connected = false;
  private connectionListeners: Set<ConnectionStatusListener> = new Set();

  // Simulate server-side message dispatching
  public dispatchMessage(message: ServerMessage) {
    if (this.listener) {
      // Simulate async behavior
      setTimeout(() => this.listener?.(message), 0);
    }
  }

  async connect(listener: MessageListener): Promise<void> {
    this.listener = listener;
    this.connected = true;
    console.log("[InMemoryTransport] Connected.");
  }

  disconnect(): void {
    this.listener = null;
    this.connected = false;
    console.log("[InMemoryTransport] Disconnected.");
  }

  async sendMessage(payload: ClientMessage): Promise<void> {
    if (!this.connected) {
      throw new Error("[InMemoryTransport] Not connected.");
    }
    console.log(`[InMemoryTransport] Sent message:`, payload);
    // In a real test setup, this might trigger a simulated server response
    // via `dispatchMessage`.
  }

  isConnected(): boolean {
    return this.connected;
  }

  onConnectionChange(listener: ConnectionStatusListener): () => void {
    this.connectionListeners.add(listener);
    return () => {
      this.connectionListeners.delete(listener);
    };
  }
}
