import type {
  Transport,
  ServerMessage,
  ClientCallbackMessage,
  ConnectionStatusListener,
} from "./transport";
import type { VDOM, VDOMNode } from "./vdom";
import { applyVDOMUpdates } from "./renderer";
import { extractEvent } from "./serialize";

type VDOMNodeListener = (node: VDOMNode) => void;

export class PulseClient {
  private vdoms: Map<string, VDOM | null>;
  private vdomListeners: Map<string, Set<VDOMNodeListener>>;
  private transport: Transport;
  private activeViews = 0;
  private connected = false;
  private disposeConnectionListener: (() => void) | null;

  constructor(transport: Transport) {
    this.transport = transport;
    this.vdoms = new Map();
    this.vdomListeners = new Map();
    this.connected = false;
    this.disposeConnectionListener = null;
  }

  public connect() {
    return new Promise<void>(async (resolve, reject) => {
      if (!this.transport.isConnected()) {
        try {
          await this.transport.connect(this.handleServerMessage);

          this.disposeConnectionListener = this.transport.onConnectionChange(
            (connected) => {
              if (connected && !this.connected) {
                for (const path of this.vdoms.keys()) {
                  this.navigate(path);
                }
              }
              this.connected = connected;
            }
          );
          resolve();
        } catch (error) {
          reject(error);
        }
      } else {
        resolve();
      }
    });
  }

  public async navigate(path: string) {
    this.activeViews += 1;
    if (this.activeViews == 1) {
      await this.connect();
    }
    // console.log("[PulseClient] Navigating to ", path);
    await this.transport.sendMessage({ type: "navigate", path });
  }

  public async leave(path: string) {
    this.activeViews -= 1;
    if (this.activeViews == 0) {
      this.disconnect();
    }
    // console.log("[PulseClient] Leaving ", path);
    await this.transport.sendMessage({ type: "leave", path });
  }

  public disconnect() {
    this.disposeConnectionListener?.();
    this.transport.disconnect();
  }

  public isConnected(): boolean {
    return this.transport.isConnected();
  }

  public onConnectionChange(listener: ConnectionStatusListener): () => void {
    return this.transport.onConnectionChange(listener);
  }

  private handleServerMessage = (message: ServerMessage) => {
    // console.log("[PulseClient] Received message:", message);
    switch (message.type) {
      case "vdom_init":
        this.vdoms.set(message.path, message.vdom);
        this.notifyVDOMListeners(message.path, this.vdoms.get(message.path)!);
        break;
      case "vdom_update":
        const currentVDOM = this.vdoms.get(message.path);
        if (!currentVDOM) {
          console.error(
            `[PulseClient] Received VDOM update for path ${message.path} before initial tree was set.`
          );
          return;
        }
        this.vdoms.set(
          message.path,
          applyVDOMUpdates(currentVDOM, message.ops)
        );
        this.notifyVDOMListeners(message.path, this.vdoms.get(message.path)!);
        break;
    }
  };

  public invokeCallback = (path: string, callback: string, args: any[]) => {
    const payload: ClientCallbackMessage = {
      type: "callback",
      path,
      callback,
      args: args.map(extractEvent),
    };
    this.transport.sendMessage(payload);
  };

  public getVDOM(path: string): VDOM | null {
    return this.vdoms.get(path) ?? null;
  }

  public subscribe(path: string, listener: VDOMNodeListener): () => void {
    if (!this.vdomListeners.has(path)) {
      this.vdomListeners.set(path, new Set());
    }
    this.vdomListeners.get(path)!.add(listener);

    // Also immediately notify the new listener with the current VDOM if it exists
    const currentVDOM = this.vdoms.get(path);
    if (currentVDOM) {
      listener(currentVDOM);
    }

    return () => {
      const listeners = this.vdomListeners.get(path);
      if (listeners) {
        listeners.delete(listener);
        if (listeners.size === 0) {
          this.vdomListeners.delete(path);
          this.vdoms.delete(path); // Clean up VDOM when no more listeners
        }
      }
    };
  }

  private notifyVDOMListeners(path: string, vdom: VDOM) {
    const listeners = this.vdomListeners.get(path);
    if (listeners) {
      const listenersArray = Array.from(listeners);
      for (const listener of listenersArray) {
        listener(vdom);
      }
    }
  }
}
