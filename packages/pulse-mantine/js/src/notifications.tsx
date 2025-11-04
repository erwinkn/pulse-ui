import {
	notificationsStore as defaultStore,
	Notifications as MantineNotifications,
	type NotificationData,
	type NotificationsProps,
	notifications as notificationsApi,
} from "@mantine/notifications";
import { usePulseChannel } from "pulse-ui-client";
import { useEffect } from "react";

type NotificationUpdatePayload = Parameters<typeof notificationsApi.update>[0];
type NotificationShowPayload = NotificationData;

export interface PulseNotificationsProps extends NotificationsProps {
	channelId?: string;
}

function isNotificationData(payload: unknown): payload is NotificationData {
	return typeof payload === "object" && payload !== null;
}

function isUpdatePayload(payload: unknown): payload is NotificationUpdatePayload {
	return isNotificationData(payload) && typeof payload.id === "string" && payload.id.length > 0;
}

export function Notifications({ channelId, ...props }: PulseNotificationsProps) {
	const { store = defaultStore, ...rest } = props;
	// biome-ignore lint/correctness/useHookAtTopLevel: channelId is not expected to change
	const channel = channelId ? usePulseChannel(channelId) : undefined;
	useEffect(() => {
		if (!channel) return;

		const cleanups = [
			channel.on("show", (payload: unknown) => {
				if (!isNotificationData(payload)) return;
				notificationsApi.show(payload as NotificationShowPayload, store);
			}),
			channel.on("update", (payload: unknown) => {
				if (!isUpdatePayload(payload)) return;
				notificationsApi.update(payload, store);
			}),
			channel.on("hide", (payload: unknown) => {
				if (!payload || typeof payload !== "object") return;
				const id = (payload as { id?: unknown }).id;
				if (typeof id === "string" && id) {
					notificationsApi.hide(id, store);
				}
			}),
			channel.on("clean", () => {
				notificationsApi.clean(store);
			}),
			channel.on("cleanQueue", () => {
				notificationsApi.cleanQueue(store);
			}),
			channel.on("updateState", (payload: unknown) => {
				if (!payload || typeof payload !== "object") return;
				const next = (payload as { notifications?: unknown }).notifications;
				if (!Array.isArray(next)) return;
				notificationsApi.updateState(store, () => next as NotificationData[]);
			}),
			store.subscribe((state) => {
				if (!channel) return;
				const notificationIds = state.notifications
					.map((item) => item.id)
					.filter((id): id is string => !!id && id.length > 0);
				const queueIds = state.queue
					.map((item) => item.id)
					.filter((id): id is string => !!id && id.length > 0);
				channel.emit("stateSync", {
					notifications: notificationIds,
					queue: queueIds,
				});
			}),
		];

		return () => {
			for (const dispose of cleanups) {
				dispose();
			}
		};
	}, [channel, store]);

	return <MantineNotifications {...rest} store={store} />;
}
