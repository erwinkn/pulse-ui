import { beforeEach, describe, expect, it, mock, vi } from "bun:test";
import React, { useEffect } from "react";
import { render } from "@testing-library/react";
import { ChannelBridge } from "./channel";

const attachHandle = vi.fn();
const detachHandle = vi.fn();

const mockClient = {
	channel(id: string) {
		return new ChannelBridge(mockClient as any, id);
	},
	attachHandle,
	detachHandle,
	isConnected: () => true,
	sendMessage: vi.fn(),
	requestChannel: vi.fn(),
};

mock.module("./pulse", () => ({
	usePulseClient: () => mockClient,
}));

describe("useChannel", () => {
	beforeEach(() => {
		attachHandle.mockClear();
		detachHandle.mockClear();
	});

	it("throws on an empty id before other hooks", async () => {
		const { useChannel } = await import("./channel");
		function Bad() {
			useChannel("");
			return null;
		}
		expect(() => render(React.createElement(Bad))).toThrow("useChannel requires a non-empty channelId");
	});

	it("registers the handle during render", async () => {
		const { useChannel } = await import("./channel");
		const order: string[] = [];
		attachHandle.mockImplementation(() => {
			order.push("attach");
		});
		function Probe() {
			useChannel("chat");
			order.push("render");
			useEffect(() => {
				order.push("effect");
			}, []);
			return null;
		}
		render(React.createElement(Probe));
		expect(order[0]).toBe("attach");
		expect(order).toContain("render");
		expect(order.indexOf("attach")).toBeLessThan(order.indexOf("render"));
	});
});
