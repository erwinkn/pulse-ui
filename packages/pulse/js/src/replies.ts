import type { ReplyMessage } from "./messages";

export interface PendingReply {
	id: string;
	promise: Promise<any>;
}

export function createRandomId(): string {
	if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
		return crypto.randomUUID().replace(/-/g, "");
	}
	return Math.random().toString(16).slice(2) + Math.random().toString(16).slice(2);
}

/** Correlation id -> promise and cancellation group. Same machine as Python `PendingReplies`. */
export function createPendingReplies() {
	const pending = new Map<
		string,
		{
			resolve: (value: any) => void;
			reject: (error: unknown) => void;
			cancelKey?: string;
		}
	>();
	return {
		pending({ cancelKey }: { cancelKey?: string } = {}): PendingReply {
			const id = createRandomId();
			const promise = new Promise<any>((resolve, reject) => {
				pending.set(id, { resolve, reject, cancelKey });
			});
			return { id, promise };
		},
		apply(message: ReplyMessage): void {
			const entry = pending.get(message.id);
			if (!entry) return;
			pending.delete(message.id);
			if (message.error != null) {
				entry.reject(new Error(String(message.error)));
			} else {
				entry.resolve(message.payload);
			}
		},
		reject(id: string, error: unknown): void {
			const entry = pending.get(id);
			if (!entry) return;
			pending.delete(id);
			entry.reject(error);
		},
		rejectWhere(cancelKey: string, error: unknown): void {
			for (const [id, entry] of pending) {
				if (entry.cancelKey !== cancelKey) continue;
				pending.delete(id);
				entry.reject(error);
			}
		},
	};
}

export type PendingReplies = ReturnType<typeof createPendingReplies>;
