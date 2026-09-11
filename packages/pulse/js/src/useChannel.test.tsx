import { beforeEach, describe, expect, it, mock, vi } from "bun:test";
import React, { Component, StrictMode, useEffect } from "react";
import { render } from "@testing-library/react";
import { ChannelBridge } from "./channel";

const attachHandle = vi.fn();
const detachHandle = vi.fn();
const handles = new Set<ChannelBridge>();

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
		handles.clear();
		attachHandle.mockImplementation((bridge: ChannelBridge) => handles.add(bridge));
		detachHandle.mockImplementation((bridge: ChannelBridge) => handles.delete(bridge));
	});

	it("throws on an empty id before other hooks", async () => {
		const { useChannel } = await import("./channel");
		function Bad() {
			useChannel("");
			return null;
		}
		expect(() => render(React.createElement(Bad))).toThrow("useChannel requires a non-empty channelId");
	});

	it("attaches in an effect after render", async () => {
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
		expect(order).toContain("render");
		expect(order.indexOf("attach")).toBeGreaterThan(order.indexOf("render"));
	});

	it("does not attach a discarded render", async () => {
		const { useChannel } = await import("./channel");
		class Boundary extends Component<{ children: React.ReactNode }, { failed: boolean }> {
			override state = { failed: false };

			static getDerivedStateFromError() {
				return { failed: true };
			}

			override render() {
				return this.state.failed ? null : this.props.children;
			}
		}
		function Broken(): React.ReactNode {
			useChannel("chat");
			throw new Error("discarded");
		}
		expect(() =>
			render(
				<Boundary>
					<Broken />
				</Boundary>,
			),
		).not.toThrow();
		expect(handles).toHaveLength(0);
		expect(attachHandle).not.toHaveBeenCalled();
	});

	it("keeps one live handle through StrictMode cleanup and detaches on unmount", async () => {
		const { useChannel } = await import("./channel");
		function Probe() {
			useChannel("chat");
			return null;
		}
		const view = render(
			<StrictMode>
				<Probe />
			</StrictMode>,
		);
		expect(handles).toHaveLength(1);
		view.unmount();
		expect(handles).toHaveLength(0);
		expect(detachHandle).toHaveBeenCalled();
	});
});
