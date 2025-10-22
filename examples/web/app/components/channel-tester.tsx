import { PulseChannelResetError, usePulseChannel } from "pulse-ui-client";
import { useCallback, useEffect, useState } from "react";

type ChannelTesterProps = {
	channelId: string;
	label: string;
};

type LogEntry = {
	id: string;
	message: string;
};

function formatPayload(payload: unknown): string {
	if (payload === undefined) return "undefined";
	if (typeof payload === "string") return payload;
	try {
		return JSON.stringify(payload);
	} catch {
		return String(payload);
	}
}

export function ChannelTester({ channelId, label }: ChannelTesterProps) {
	const bridge = usePulseChannel(channelId);
	const [logs, setLogs] = useState<LogEntry[]>([]);
	const [eventCount, setEventCount] = useState(0);
	const [requestCount, setRequestCount] = useState(0);
	const [pendingRequest, setPendingRequest] = useState(false);

	const appendLog = useCallback((message: string) => {
		const entry: LogEntry = {
			id: `${Date.now()}-${Math.random()}`,
			message,
		};
		setLogs((current) => {
			const next = [entry, ...current];
			return next.slice(0, 50);
		});
	}, []);

	useEffect(() => {
		appendLog(`Mounted channel "${label}" (${channelId})`);
		return () => {
			appendLog(`Unmounted channel "${label}" (${channelId})`);
		};
	}, [appendLog, channelId, label]);

	useEffect(() => {
		const offNotify = bridge.on("server:notify", (payload) => {
			appendLog(`[server → client] notify ${formatPayload(payload)}`);
		});
		const offAsk = bridge.on("server:ask", async (payload) => {
			appendLog(`[server → client] request ${formatPayload(payload)}`);
			return {
				label,
				received: payload,
				at: new Date().toISOString(),
			};
		});
		return () => {
			offNotify();
			offAsk();
		};
	}, [appendLog, bridge, label]);

	const sendPing = useCallback(() => {
		const next = eventCount + 1;
		setEventCount(next);
		try {
			bridge.emit("client:ping", {
				label,
				sequence: next,
				at: new Date().toISOString(),
			});
			appendLog(`[client → server] ping ${label}#${next}`);
		} catch (error) {
			if (error instanceof PulseChannelResetError) {
				appendLog(`[client → server] ping failed (channel closed)`);
			} else {
				appendLog(`[client → server] ping failed ${formatPayload(error)}`);
			}
		}
	}, [appendLog, bridge, eventCount, label]);

	const sendRequest = useCallback(async () => {
		setRequestCount((count) => count + 1);
		const sequence = requestCount + 1;
		setPendingRequest(true);
		try {
			const response = await bridge.request("client:request", {
				label,
				sequence,
				at: new Date().toISOString(),
			});
			appendLog(`[client → server] request #${sequence} resolved ${formatPayload(response)}`);
		} catch (error) {
			if (error instanceof PulseChannelResetError) {
				appendLog(`[client → server] request #${sequence} failed (channel closed)`);
			} else {
				appendLog(`[client → server] request #${sequence} failed ${formatPayload(error)}`);
			}
		} finally {
			setPendingRequest(false);
		}
	}, [appendLog, bridge, label, requestCount]);

	const clearLogs = useCallback(() => {
		setLogs([]);
	}, []);

	return (
		<div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm space-y-3">
			<div className="flex items-start justify-between gap-3">
				<div className="space-y-1">
					<p className="text-sm uppercase tracking-wide text-slate-500">Channel Tester</p>
					<h3 className="text-lg font-semibold text-slate-900">{label}</h3>
					<p className="text-xs font-mono text-slate-500">channel: {channelId}</p>
				</div>
				<button type="button" onClick={clearLogs} className="btn-light btn-xs">
					Clear log
				</button>
			</div>
			<div className="flex flex-wrap gap-2">
				<button type="button" onClick={sendPing} className="btn-primary btn-sm">
					Send ping
				</button>
				<button
					type="button"
					onClick={sendRequest}
					className="btn-secondary btn-sm"
					disabled={pendingRequest}
				>
					{pendingRequest ? "Waiting..." : "Send request"}
				</button>
			</div>
			<div className="max-h-56 overflow-auto rounded-md border border-slate-200 bg-slate-950 p-3 text-xs text-slate-100">
				{logs.length === 0 ? (
					<p className="text-slate-400">No messages yet</p>
				) : (
					<ul className="space-y-2">
						{logs.map((entry, index) => (
							<li key={entry.id}>
								<span className="text-slate-500">{logs.length - index}.</span> {entry.message}
							</li>
						))}
					</ul>
				)}
			</div>
		</div>
	);
}
