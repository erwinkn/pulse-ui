import type {
  Transport,
  ServerMessage,
  ClientCallbackMessage,
  ClientNavigateMessage,
} from "./transport";
import { FRAGMENT_TAG, type VDOM } from "./vdom";
import { applyUpdates } from "./renderer";

type VDOMListener = (vdom: VDOM) => void;

export class PulseClient {
  private vdom: VDOM;
  private vdomListeners: Set<VDOMListener> = new Set();
  private transport: Transport;

  constructor(transport: Transport, initialVDOM: VDOM) {
    this.transport = transport;
    this.vdom = initialVDOM;
  }

  public async connect(initialRoute: string) {
    await this.transport.connect(this.handleMessage);
    this.navigate(initialRoute);
  }

  public disconnect() {
    this.transport.disconnect();
    // TODO: do we need to do this?
    this.vdom = { tag: FRAGMENT_TAG, children: [], props: {} };
    this.notifyVDOMListeners();
  }

  private handleMessage = (message: ServerMessage) => {
    switch (message.type) {
      case "vdom_init":
        this.vdom = message.vdom;
        break;
      case "vdom_update":
        if (!this.vdom) {
          console.error(
            "[PulseClient] Received VDOM update before initial tree was set."
          );
          return;
        }
        this.vdom = applyUpdates(this.vdom, message.ops);
        break;
      default:
        // Ensure all message types are handled
        const exhaustiveCheck: never = message;
        throw new Error(`Unhandled message type: ${exhaustiveCheck}`);
    }
    this.notifyVDOMListeners();
  };

  public navigate(route: string): void {
    console.log("Navigating to ", route);
    const payload: ClientNavigateMessage = { type: "navigate", route };
    this.transport.sendMessage(payload);
  }

  public invokeCallback = (callback: string, ...args: any[]) => {
    const payload: ClientCallbackMessage = { type: "callback", callback, args };
    this.transport.sendMessage(payload);
  };

  public getVDOM() {
    return this.vdom;
  }

  public subscribe(listener: VDOMListener): () => void {
    this.vdomListeners.add(listener);
    // Return an unsubscribe function
    return () => {
      this.vdomListeners.delete(listener);
    };
  }

  private notifyVDOMListeners() {
    // Create a shallow copy for iteration to avoid issues if a listener
    // unsubscribes as a result of being called.
    const listeners = Array.from(this.vdomListeners);
    for (const listener of listeners) {
      listener(this.vdom);
    }
  }
}
