import { useEffect, useMemo } from "react";
import { usePulseClient } from "./pulse";
import type { ChannelBridge } from "./channel";

export function usePulseChannel(channelId: string): ChannelBridge {
  const client = usePulseClient();
  const bridge = useMemo(() => {
    if (!channelId) {
      throw new Error("usePulseChannel requires a non-empty channelId");
    }
    return client.acquireChannel(channelId);
  }, [client, channelId]);

  useEffect(() => {
    return () => {
      client.releaseChannel(channelId);
    };
  }, [client, channelId]);

  return bridge;
}
