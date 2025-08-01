import type {
  Transport,
  ServerMessage,
  ClientCallbackMessage,
  ClientNavigateMessage,
} from "./transport";
import type { VDOM, VDOMNode } from "./vdom";
import { applyVDOMUpdates } from "./renderer";

type VDOMNodeListener = (node: VDOMNode) => void;

export class PulseClient {
  private vdom: VDOM | null;
  private vdomListeners: Set<VDOMNodeListener> = new Set();
  private transport: Transport;

  constructor(transport: Transport) {
    console.warn("Creating new PulseClient");
    this.transport = transport;
    this.vdom = null;
  }

  public async connect() {
    if (!this.transport.isConnected()) {
      await this.transport.connect(this.handleServerMessage);
    }
  }

  public async navigate(route: string) {
    await this.connect();
    console.log("[PulseClient] Navigating to ", route);
    await this.transport.sendMessage({ type: "navigate", route });
  }

  public disconnect() {
    this.transport.disconnect();
  }

  private handleServerMessage = (message: ServerMessage) => {
    console.log("[PulseClient] Received message:", message);
    switch (message.type) {
      case "vdom_init":
        this.vdom = message.vdom;
        this.notifyVDOMListeners(this.vdom);
        break;
      case "vdom_update":
        if (!this.vdom) {
          console.error(
            "[PulseClient] Received VDOM update before initial tree was set."
          );
          return;
        }
        this.vdom = applyVDOMUpdates(this.vdom, message.ops);
        this.notifyVDOMListeners(this.vdom);
        break;
    }
  };

  public invokeCallback = (callback: string, args: any[]) => {
    const payload: ClientCallbackMessage = {
      type: "callback",
      callback,
      args,
    };
    this.transport.sendMessage(payload);
  };

  public subscribe(listener: VDOMNodeListener): () => void {
    this.vdomListeners.add(listener);
    return () => {
      this.vdomListeners.delete(listener);
    };
  }

  private notifyVDOMListeners(vdom: VDOM) {
    const listeners = Array.from(this.vdomListeners);
    for (const listener of listeners) {
      listener(vdom);
    }
  }
}
