import type { UINode, UIUpdatePayload } from "./tree";

export interface TransportMessage {
  type: "ui_updates" | "ui_tree" | "callback_invoke" | "ping" | "pong";
  updates?: UIUpdatePayload[];
  tree?: UINode;
  callback_key?: string;
  request_id?: string;
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

  send(message: TransportMessage): void {
    console.log("EventEmitterTransport send:", message);
    // For local testing, immediately dispatch the message back to the handler
    if (this.messageCallback) {
      // Use setTimeout to make this async like a real transport
      setTimeout(() => {
        if (this.messageCallback) {
          this.messageCallback(message);
        }
      }, 0);
    }
  }

  onMessage(callback: (message: TransportMessage) => void): void {
    this.messageCallback = callback;
  }

  // Method to dispatch messages directly to this transport (for testing)
  dispatchMessage(message: TransportMessage): void {
    console.log("EventEmitterTransport dispatchMessage:", message);
    if (this.messageCallback) {
      // Use setTimeout to make this async like a real transport
      setTimeout(() => {
        if (this.messageCallback) {
          this.messageCallback(message);
        }
      }, 0);
    }
  }

  close(): void {
    this.messageCallback = null;
  }
}
