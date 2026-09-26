import { describe, expect, it, vi } from "bun:test";
import { render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { PulseSocketIOClient } from "./client";
import { PulseProvider, PulseView, usePulseChannel, usePulseViewId } from "./pulse";
import { PulseRouterProvider } from "./router";

vi.mock("socket.io-client", () => ({
	io: () => ({
		connected: false,
		disconnect: vi.fn(),
		emit: vi.fn(),
		on: vi.fn(),
	}),
}));

describe("PulseView channel hooks", () => {
	it("provides view id context and returns null before channel effect runs", async () => {
		const states: Array<{ viewId: string; channel: string | null }> = [];

		function Probe() {
			const viewId = usePulseViewId();
			const channel = usePulseChannel("chan-1");
			states.push({ viewId, channel: channel?.id ?? null });
			return <div data-testid="channel">{channel?.id ?? "null"}</div>;
		}

		const client = new PulseSocketIOClient("http://pulse.test", {}, {
			initialConnectingDelay: 100000,
			initialErrorDelay: 100000,
			reconnectErrorDelay: 100000,
		});

		render(
			<PulseRouterProvider
				routes={[{ id: "/test", path: "test" }]}
				routeLoaders={{}}
				initialUrl="http://pulse.test/test"
			>
				<PulseProvider
					client={client}
					prerender={{
						directives: {},
						views: {
							"/test": {
								view: "view-1",
								routePath: "/test",
								vdom: { tag: "$$Probe" },
							},
						},
					}}
				>
					<PulseView path="/test" registry={{ Probe }} />
				</PulseProvider>
			</PulseRouterProvider>,
		);

		await waitFor(() => {
			expect(screen.getByTestId("channel")).toHaveTextContent("chan-1");
		});
		expect(states[0]).toEqual({ viewId: "view-1", channel: null });
		expect(states.at(-1)).toEqual({ viewId: "view-1", channel: "chan-1" });
	});
});
