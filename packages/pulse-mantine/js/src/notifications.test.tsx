import { expect, it, mock } from "bun:test";
import { MantineProvider } from "@mantine/core";
import { render } from "@testing-library/react";

const channel = {
	closed: false,
	on: mock(() => () => {}),
	emit: mock(() => {}),
};
const acquireChannel = mock((_id: string) => channel);
const releaseChannel = mock(() => {});
const usePulseChannelOwner = mock(() => ({
	token: "/current-route",
	attachPath: "/current-route",
}));
class PulseChannelResetError extends Error {}

mock.module("pulse-ui-client", () => ({
	PulseChannelResetError,
	submitForm: mock(() => {}),
	usePulseChannelOwner,
	usePulseClient: () => ({ acquireChannel, releaseChannel }),
	usePulseDirectivesSource: () => undefined,
}));

const { Notifications } = await import("./notifications");

it("subscribes to its tab channel without route ownership", () => {
	const view = render(
		<MantineProvider>
			<Notifications channelId="notifications-tab" />
		</MantineProvider>,
	);

	expect(acquireChannel.mock.calls).toEqual([["notifications-tab"]]);
	expect(usePulseChannelOwner).not.toHaveBeenCalled();

	view.unmount();
	expect(releaseChannel).toHaveBeenCalledWith("notifications-tab", channel);
});
