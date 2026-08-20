import { expect, it, mock } from "bun:test";
import { MantineProvider } from "@mantine/core";
import { render } from "@testing-library/react";

const channel = {
	closed: false,
	on: mock(() => () => {}),
	emit: mock(() => {}),
};
const usePulseChannel = mock((_id: string, _lifetime?: string) => channel);

mock.module("pulse-ui-client", () => ({
	PulseChannelResetError: class PulseChannelResetError extends Error {},
	submitForm: mock(() => {}),
	usePulseChannel,
	usePulseChannelOwner: mock(() => ({
		token: "/current-route",
		attachPath: "/current-route",
	})),
	usePulseClient: () => ({}),
	usePulseDirectivesSource: () => undefined,
}));

const { Notifications } = await import("./notifications");

it("subscribes to its tab channel without route ownership", () => {
	const view = render(
		<MantineProvider>
			<Notifications channelId="notifications-tab" />
		</MantineProvider>,
	);

	expect(usePulseChannel.mock.calls).toEqual([["notifications-tab", "tab"]]);

	view.unmount();
});
