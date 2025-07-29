import type { UINode, UIUpdatePayload } from "./types";

export interface TransportMessage {
  type: "ui_updates" | "ui_tree" | "custom" | "callback_invoke" | "callback_response" | "ping" | "pong" | "get_callbacks" | "callbacks_list" | "error";
  updates?: UIUpdatePayload[];
  tree?: UINode;
  data?: any;
  // Callback-specific fields
  callback_key?: string;
  request_id?: string;
  success?: boolean;
  callbacks?: string[];
  message?: string;
}

export interface Transport {
  send(message: TransportMessage): void;
  onMessage(callback: (message: TransportMessage) => void): void;
  close(): void;
}

export class WebSocketTransport implements Transport {
  private ws: WebSocket | null = null;
  private messageCallback: ((message: TransportMessage) => void) | null = null;

  constructor(private url: string) {
    this.connect();
  }

  private connect() {
    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      console.log(`WebSocket connected to ${this.url}`);
    };

    this.ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data) as TransportMessage;
        if (this.messageCallback) {
          this.messageCallback(message);
        }
      } catch (error) {
        console.error("Error parsing WebSocket message:", error);
      }
    };

    this.ws.onerror = (error) => {
      console.error("WebSocket error:", error);
    };

    this.ws.onclose = () => {
      console.log("WebSocket disconnected");
    };
  }

  send(message: TransportMessage): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      console.log("Sending websocket message:", message);
      this.ws.send(JSON.stringify(message));
    } else {
      console.log("WebSocket not open");
    }
  }

  onMessage(callback: (message: TransportMessage) => void): void {
    this.messageCallback = callback;
  }

  close(): void {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}

export class EventEmitterTransport implements Transport {
  private messageCallback: ((message: TransportMessage) => void) | null = null;
  private eventTarget = new EventTarget();

  constructor() {
    this.eventTarget.addEventListener("message", (event) => {
      if (this.messageCallback) {
        this.messageCallback((event as CustomEvent).detail);
      }
    });
  }

  send(message: TransportMessage): void {
    // In a real app, this might send to a different EventEmitterTransport instance
    console.log("EventEmitterTransport send:", message);
  }

  onMessage(callback: (message: TransportMessage) => void): void {
    this.messageCallback = callback;
  }

  // Method to dispatch messages to this transport
  dispatchMessage(message: TransportMessage): void {
    this.eventTarget.dispatchEvent(
      new CustomEvent("message", { detail: message })
    );
  }

  close(): void {
    this.messageCallback = null;
  }
}
