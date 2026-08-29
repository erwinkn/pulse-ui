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
export class PendingReplies {
	private entries = new Map<
		string,
		{
			resolve: (value: any) => void;
			reject: (error: unknown) => void;
			cancelKey?: string;
		}
	>();

	pending({ cancelKey }: { cancelKey?: string } = {}): PendingReply {
		const id = createRandomId();
		const promise = new Promise<any>((resolve, reject) => {
			this.entries.set(id, { resolve, reject, cancelKey });
		});
		return { id, promise };
	}

	apply(message: ReplyMessage): void {
		const entry = this.entries.get(message.id);
		if (!entry) return;
		this.entries.delete(message.id);
		if (message.error != null) {
			entry.reject(new Error(String(message.error)));
		} else {
			entry.resolve(message.payload);
		}
	}

	reject(id: string, error: unknown): void {
		const entry = this.entries.get(id);
		if (!entry) return;
		this.entries.delete(id);
		entry.reject(error);
	}

	rejectWhere(cancelKey: string, error: unknown): void {
		for (const [id, entry] of this.entries) {
			if (entry.cancelKey !== cancelKey) continue;
			this.entries.delete(id);
			entry.reject(error);
		}
	}
}
