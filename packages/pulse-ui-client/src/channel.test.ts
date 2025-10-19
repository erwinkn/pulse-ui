import { describe, it, expect, vi } from "vitest";

import type { ClientChannelMessage } from "./messages";
import { createChannelBridge, PulseChannelResetError } from "./channel";

function makeClient() {
  const sent: ClientChannelMessage[] = [];
  const sendMessage = vi.fn(async (message: ClientChannelMessage) => {
    sent.push(message);
  });
  const client = { sendMessage } as any;
  const bridge = createChannelBridge(client, "chan-1");
  return { bridge, sent, sendMessage };
}

describe("ChannelBridge", () => {
  it("queues request and resolves on response", async () => {
    const { bridge, sent } = makeClient();
    const pending = bridge.request("echo", { foo: 1 });
    expect(sent).toHaveLength(1);
    const requestId = sent[0]!.requestId!;
    bridge.handleServerMessage({
      type: "channel_message",
      channel: "chan-1",
      responseTo: requestId,
      payload: { foo: 2 },
    });
    await expect(pending).resolves.toEqual({ foo: 2 });
  });

  it("dispatches events to registered handlers", () => {
    const { bridge } = makeClient();
    const handler = vi.fn();
    bridge.on("ping", handler);
    bridge.handleServerMessage({
      type: "channel_message",
      channel: "chan-1",
      event: "ping",
      payload: { value: 42 },
    });
    expect(handler).toHaveBeenCalledWith({ value: 42 });
  });

  it("responds to server requests", async () => {
    const { bridge, sendMessage } = makeClient();
    bridge.on("compute", () => 99);
    bridge.handleServerMessage({
      type: "channel_message",
      channel: "chan-1",
      event: "compute",
      requestId: "req-1",
      payload: {},
    });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(sendMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        responseTo: "req-1",
        payload: 99,
        event: undefined,
      })
    );
  });

  it("rejects pending requests when closed", async () => {
    const { bridge } = makeClient();
    const pending = bridge.request("close-me");
    bridge.handleServerMessage({
      type: "channel_message",
      channel: "chan-1",
      event: "__close__",
    });
    await expect(pending).rejects.toBeInstanceOf(PulseChannelResetError);
  });
});
