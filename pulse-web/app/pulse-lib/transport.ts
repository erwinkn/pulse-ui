import { io, Socket } from "socket.io-client";
import type { VDOMNode, VDOMUpdate } from "./vdom";

// =================================================================
// Message Types
// =================================================================

// Based on pulse/messages.py
export interface ServerInitMessage {
  type: "vdom_init";
  vdom: VDOMNode;
}

export interface ServerUpdateMessage {
  type: "vdom_update";
  ops: VDOMUpdate[];
}

export type ServerMessage = ServerInitMessage | ServerUpdateMessage;

export interface ClientCallbackMessage {
  type: "callback";
  callback: string;
  args: any[];
}

export interface ClientNavigateMessage {
  type: "navigate";
  route: string;
}

export type ClientMessage = ClientCallbackMessage | ClientNavigateMessage;

// =================================================================
// Transport Abstraction
// =================================================================

export type MessageListener = (message: ServerMessage) => void;

export interface Transport {
  connect(listener: MessageListener): Promise<void>;
  disconnect(): void;
  sendMessage(payload: ClientMessage): Promise<void>;
  isConnected(): boolean;
}

// =================================================================
// Socket.IO Transport
// =================================================================

export class SocketIOTransport implements Transport {
  private socket: Socket | null = null;
  private listener: MessageListener | null = null;

  constructor(private url: string) {}

  connect(listener: MessageListener): Promise<void> {
    this.listener = listener;
    return new Promise((resolve, reject) => {
      this.socket = io(this.url, {
        transports: ["websocket"],
      });

      this.socket.on("connect", () => {
        console.log("[SocketIOTransport] Connected:", this.socket?.id);
        resolve();
      });

      this.socket.on("connect_error", (err) => {
        console.error("[SocketIOTransport] Connection failed:", err);
        reject(err);
      });

      this.socket.on("disconnect", () => {
        console.log("[SocketIOTransport] Disconnected");
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
  }

  async sendMessage(payload: ClientMessage): Promise<void> {
    if (!this.socket || !this.socket.connected) {
      throw new Error("[SocketIOTransport] Not connected.");
    }
    console.log("[SocketIOTransport] Sending:", payload);
    this.socket.emit("message", payload);
  }

  isConnected(): boolean {
    return this.socket?.connected || false;
  }
}

// =================================================================
// In-Memory Transport (for testing)
// =================================================================

export class InMemoryTransport implements Transport {
  private listener: MessageListener | null = null;
  private connected = false;

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
}
