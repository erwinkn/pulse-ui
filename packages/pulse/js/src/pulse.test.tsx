import { describe, expect, it, vi } from "bun:test";
import { render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { MemoryRouter } from "react-router";
import { PulseProvider, PulseView, usePulseChannel, usePulseViewPath } from "./pulse";

vi.mock("socket.io-client", () => ({
	io: () => ({
		connected: false,
		disconnect: vi.fn(),
		emit: vi.fn(),
		on: vi.fn(),
	}),
}));

describe("PulseView channel hooks", () => {
	it("provides view path context and returns null before channel effect runs", async () => {
		const states: Array<{ path: string; channel: string | null }> = [];

		function Probe() {
			const path = usePulseViewPath();
			const channel = usePulseChannel("chan-1");
			states.push({ path, channel: channel?.id ?? null });
			return <div data-testid="channel">{channel?.id ?? "null"}</div>;
		}

		render(
			<MemoryRouter initialEntries={["/test"]}>
				<PulseProvider
					config={{
						serverAddress: "http://pulse.test",
						apiPrefix: "/api",
						connectionStatus: {
							initialConnectingDelay: 100000,
							initialErrorDelay: 100000,
							reconnectErrorDelay: 100000,
						},
					}}
					prerender={{
						directives: {},
						views: {
							"/test": {
								vdom: { tag: "$$Probe" },
							},
						},
					}}
				>
					<PulseView path="/test" registry={{ Probe }} />
				</PulseProvider>
			</MemoryRouter>,
		);

		await waitFor(() => {
			expect(screen.getByTestId("channel")).toHaveTextContent("chan-1");
		});
		expect(states[0]).toEqual({ path: "/test", channel: null });
		expect(states.at(-1)).toEqual({ path: "/test", channel: "chan-1" });
	});
});
