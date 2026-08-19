import type { ReplyMessage } from "./messages";

/** Correlation id -> promise. Same machine as Python `PendingReplies`. */
export function createPendingReplies() {
	const pending = new Map<
		string,
		{ resolve: (value: any) => void; reject: (error: unknown) => void }
	>();
	return {
		register(id: string): Promise<any> {
			return new Promise((resolve, reject) => {
				pending.set(id, { resolve, reject });
			});
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
	};
}

export type PendingReplies = ReturnType<typeof createPendingReplies>;
