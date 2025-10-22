import { useEffect, useMemo } from "react";
import type { ChannelBridge } from "./channel";
import { usePulseClient } from "./pulse";

export function usePulseChannel(channelId: string): ChannelBridge {
	const client = usePulseClient();
	const bridge = useMemo(() => {
		if (!channelId) {
			throw new Error("usePulseChannel requires a non-empty channelId");
		}
		console.log(`Acquiring channel ${channelId}`);
		return client.acquireChannel(channelId);
	}, [client, channelId]);

	useEffect(() => {
		return () => {
			console.log(`Releasing channel ${channelId}`);
			client.releaseChannel(channelId);
		};
	}, [client, channelId]);

	return bridge;
}
