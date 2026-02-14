import {
	type CSSProperties,
	type KeyboardEvent as ReactKeyboardEvent,
	type MouseEvent as ReactMouseEvent,
	useEffect,
	useMemo,
	useRef,
	useState,
} from "react";
import type { ServerError } from "./messages";

const MAX_ERROR_HISTORY = 25;
const STACK_PREVIEW_LINES = 18;
const MESSAGE_TRUNCATE_CHARS = 360;

export interface ServerErrorOverlayEntry {
	error: ServerError;
	fingerprint: string;
	repeatCount: number;
	receivedAt: number;
}

export interface ServerErrorOverlayState {
	entries: ServerErrorOverlayEntry[];
	activeIndex: number;
	isOpen: boolean;
}

export type ServerErrorOverlayAction =
	| { type: "init" }
	| { type: "update" }
	| { type: "error"; error: ServerError }
	| { type: "dismiss" }
	| { type: "previous" }
	| { type: "next" }
	| { type: "select"; index: number };

export interface ServerErrorOverlayProps {
	entry: ServerErrorOverlayEntry;
	activeIndex: number;
	errorCount: number;
	onClose: () => void;
	onPrevious?: () => void;
	onNext?: () => void;
}

export const INITIAL_SERVER_ERROR_OVERLAY_STATE: ServerErrorOverlayState = {
	entries: [],
	activeIndex: 0,
	isOpen: false,
};

function clamp(value: number, min: number, max: number): number {
	if (value < min) return min;
	if (value > max) return max;
	return value;
}

export function getServerErrorFingerprint(error: ServerError): string {
	return `${error.code}|${error.message}|${error.stack ?? ""}`;
}

export function reduceServerErrorOverlay(
	current: ServerErrorOverlayState,
	action: ServerErrorOverlayAction,
): ServerErrorOverlayState {
	switch (action.type) {
		case "init":
			return INITIAL_SERVER_ERROR_OVERLAY_STATE;
		case "update":
			return current;
		case "dismiss":
			return {
				...current,
				isOpen: false,
			};
		case "previous": {
			if (current.entries.length === 0) return current;
			const maxIndex = current.entries.length - 1;
			return {
				...current,
				activeIndex: clamp(current.activeIndex - 1, 0, maxIndex),
			};
		}
		case "next": {
			if (current.entries.length === 0) return current;
			const maxIndex = current.entries.length - 1;
			return {
				...current,
				activeIndex: clamp(current.activeIndex + 1, 0, maxIndex),
			};
		}
		case "select": {
			if (current.entries.length === 0) return current;
			const maxIndex = current.entries.length - 1;
			return {
				...current,
				activeIndex: clamp(action.index, 0, maxIndex),
			};
		}
		case "error": {
			const fingerprint = getServerErrorFingerprint(action.error);
			const receivedAt = Date.now();
			const last = current.entries[current.entries.length - 1];
			let entries = current.entries;

			if (last && last.fingerprint === fingerprint) {
				const updated: ServerErrorOverlayEntry = {
					...last,
					error: action.error,
					repeatCount: last.repeatCount + 1,
					receivedAt,
				};
				entries = [...current.entries.slice(0, -1), updated];
			} else {
				const next: ServerErrorOverlayEntry = {
					error: action.error,
					fingerprint,
					repeatCount: 1,
					receivedAt,
				};
				entries = [...current.entries, next];
			}

			if (entries.length > MAX_ERROR_HISTORY) {
				entries = entries.slice(entries.length - MAX_ERROR_HISTORY);
			}

			return {
				entries,
				activeIndex: entries.length - 1,
				isOpen: true,
			};
		}
	}
}

export function getActiveServerErrorOverlayEntry(
	state: ServerErrorOverlayState,
): ServerErrorOverlayEntry | null {
	if (state.entries.length === 0) return null;
	return state.entries[clamp(state.activeIndex, 0, state.entries.length - 1)] ?? null;
}

function isInternalStackLine(line: string): boolean {
	const normalized = line.toLowerCase();
	return (
		normalized.includes("node_modules") ||
		normalized.includes("webpack-internal") ||
		normalized.includes("internal/") ||
		normalized.includes("<anonymous>") ||
		normalized.startsWith("at node:") ||
		normalized.startsWith("at bun:")
	);
}

function formatErrorForClipboard(entry: ServerErrorOverlayEntry): string {
	const { error } = entry;
	const parts = [
		`Code: ${error.code}`,
		`Message: ${error.message}`,
		entry.repeatCount > 1 ? `Occurrences: ${entry.repeatCount}` : "",
		error.stack ? `\nStack:\n${error.stack}` : "",
		error.details ? `\nDetails:\n${JSON.stringify(error.details, null, 2)}` : "",
	].filter(Boolean);
	return parts.join("\n");
}

function smallButtonStyle(disabled = false): CSSProperties {
	return {
		padding: "6px 10px",
		border: "1px solid #d1d5db",
		borderRadius: 8,
		background: disabled ? "#f3f4f6" : "#ffffff",
		color: "#111827",
		cursor: disabled ? "not-allowed" : "pointer",
		opacity: disabled ? 0.5 : 1,
		fontSize: 12,
		fontWeight: 600,
	};
}

export function ServerErrorOverlay({
	entry,
	activeIndex,
	errorCount,
	onClose,
	onPrevious,
	onNext,
}: ServerErrorOverlayProps) {
	const [messageExpanded, setMessageExpanded] = useState(false);
	const [stackExpanded, setStackExpanded] = useState(false);
	const [showInternalFrames, setShowInternalFrames] = useState(false);
	const [copied, setCopied] = useState(false);
	const closeButtonRef = useRef<HTMLButtonElement | null>(null);

	useEffect(() => {
		setMessageExpanded(false);
		setStackExpanded(false);
		setShowInternalFrames(false);
		setCopied(false);
	}, [entry.fingerprint]);

	useEffect(() => {
		const activeBeforeOpen = document.activeElement as HTMLElement | null;
		closeButtonRef.current?.focus();
		return () => {
			activeBeforeOpen?.focus?.();
		};
	}, []);

	useEffect(() => {
		const onKeyDown = (event: KeyboardEvent) => {
			if (event.key === "Escape") {
				event.preventDefault();
				onClose();
			}
		};
		window.addEventListener("keydown", onKeyDown);
		return () => {
			window.removeEventListener("keydown", onKeyDown);
		};
	}, [onClose]);

	const stackLines = useMemo(() => {
		if (!entry.error.stack) return [] as string[];
		return entry.error.stack
			.split("\n")
			.map((line) => line.trimEnd())
			.filter((line) => line.length > 0);
	}, [entry.error.stack]);

	const internalCount = useMemo(
		() => stackLines.reduce((count, line) => count + (isInternalStackLine(line) ? 1 : 0), 0),
		[stackLines],
	);

	const visibleStackLines = useMemo(() => {
		if (showInternalFrames) return stackLines;
		return stackLines.filter((line) => !isInternalStackLine(line));
	}, [stackLines, showInternalFrames]);

	const displayedStackLines = stackExpanded
		? visibleStackLines
		: visibleStackLines.slice(0, STACK_PREVIEW_LINES);

	const stackNeedsExpand = visibleStackLines.length > STACK_PREVIEW_LINES;
	const message = entry.error.message ?? "";
	const isLongMessage = message.length > MESSAGE_TRUNCATE_CHARS;
	const shownMessage =
		!isLongMessage || messageExpanded
			? message
			: `${message.slice(0, MESSAGE_TRUNCATE_CHARS).trimEnd()}...`;

	const handleBackdropMouseDown = (event: ReactMouseEvent<HTMLDivElement>) => {
		if (event.target === event.currentTarget) {
			onClose();
		}
	};

	const handlePanelKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
		if (event.key === "Escape") {
			event.preventDefault();
			onClose();
		}
	};

	const handleCopy = () => {
		const text = formatErrorForClipboard(entry);
		if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
			void navigator.clipboard.writeText(text).catch(() => {});
		}
		setCopied(true);
	};

	return (
		<div
			data-testid="server-error-overlay-backdrop"
			onMouseDown={handleBackdropMouseDown}
			style={{
				position: "fixed",
				inset: 0,
				padding: 20,
				background: "rgba(2, 6, 23, 0.55)",
				zIndex: 2147483647,
				overflow: "auto",
			}}
		>
			<div
				data-testid="server-error-overlay-panel"
				role="dialog"
				aria-modal="true"
				aria-labelledby="pulse-server-error-overlay-title"
				onKeyDown={handlePanelKeyDown}
				style={{
					maxWidth: 980,
					margin: "20px auto",
					background: "#fff",
					color: "#111827",
					borderRadius: 14,
					border: "1px solid #fecaca",
					boxShadow: "0 20px 45px rgba(0, 0, 0, 0.38)",
					fontFamily:
						'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
				}}
			>
				<div
					style={{
						display: "flex",
						alignItems: "center",
						justifyContent: "space-between",
						gap: 12,
						padding: "14px 16px",
						borderBottom: "1px solid #e5e7eb",
					}}
				>
					<div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
						<span
							id="pulse-server-error-overlay-title"
							style={{
								fontWeight: 800,
								fontSize: 14,
								color: "#991b1b",
								background: "#fee2e2",
								border: "1px solid #fecaca",
								borderRadius: 999,
								padding: "4px 10px",
							}}
						>
							Server Error: {entry.error.code}
						</span>
						<span style={{ fontSize: 12, color: "#4b5563", fontWeight: 700 }}>
							{activeIndex + 1} of {errorCount}
							{entry.repeatCount > 1 ? `  x${entry.repeatCount}` : ""}
						</span>
					</div>
					<div style={{ display: "flex", alignItems: "center", gap: 8 }}>
						<button
							type="button"
							onClick={onPrevious}
							disabled={!onPrevious}
							style={smallButtonStyle(!onPrevious)}
						>
							Prev
						</button>
						<button
							type="button"
							onClick={onNext}
							disabled={!onNext}
							style={smallButtonStyle(!onNext)}
						>
							Next
						</button>
						<button type="button" onClick={handleCopy} style={smallButtonStyle(false)}>
							{copied ? "Copied" : "Copy"}
						</button>
						<button
							ref={closeButtonRef}
							type="button"
							onClick={onClose}
							aria-label="Close error overlay"
							style={{
								...smallButtonStyle(false),
								padding: "6px 9px",
								fontSize: 14,
								lineHeight: 1,
							}}
						>
							x
						</button>
					</div>
				</div>

				<div style={{ padding: 16 }}>
					<div style={{ marginBottom: 14 }}>
						<div style={{ color: "#7f1d1d", fontWeight: 700, marginBottom: 6 }}>Message</div>
						<pre
							style={{
								margin: 0,
								whiteSpace: "pre-wrap",
								wordBreak: "break-word",
								fontSize: 13,
								color: "#111827",
							}}
						>
							{shownMessage}
						</pre>
						{isLongMessage && (
							<button
								data-testid="server-error-overlay-message-toggle"
								type="button"
								onClick={() => setMessageExpanded((v) => !v)}
								style={{ ...smallButtonStyle(false), marginTop: 8 }}
							>
								{messageExpanded ? "Show less" : "Show more"}
							</button>
						)}
					</div>

					{stackLines.length > 0 && (
						<div style={{ marginBottom: 14 }}>
							<div
								style={{
									display: "flex",
									alignItems: "center",
									justifyContent: "space-between",
									gap: 8,
									marginBottom: 6,
								}}
							>
								<div style={{ color: "#7f1d1d", fontWeight: 700 }}>Stack trace</div>
								<div style={{ display: "flex", gap: 8 }}>
									{internalCount > 0 && (
										<button
											data-testid="server-error-overlay-internal-toggle"
											type="button"
											onClick={() => setShowInternalFrames((v) => !v)}
											style={smallButtonStyle(false)}
										>
											{showInternalFrames
												? "Hide internal frames"
												: `Show internal frames (${internalCount})`}
										</button>
									)}
									{stackNeedsExpand && (
										<button
											data-testid="server-error-overlay-stack-toggle"
											type="button"
											onClick={() => setStackExpanded((v) => !v)}
											style={smallButtonStyle(false)}
										>
											{stackExpanded ? "Show less" : "Show more"}
										</button>
									)}
								</div>
							</div>
							<pre
								data-testid="server-error-overlay-stack"
								style={{
									margin: 0,
									padding: 10,
									borderRadius: 8,
									background: "#f9fafb",
									border: "1px solid #e5e7eb",
									fontSize: 12,
									lineHeight: 1.45,
									maxHeight: 350,
									overflow: "auto",
								}}
							>
								{displayedStackLines.join("\n")}
							</pre>
						</div>
					)}

					{entry.error.details && (
						<details>
							<summary style={{ cursor: "pointer", fontWeight: 700, color: "#7f1d1d" }}>
								Details
							</summary>
							<pre
								style={{
									marginTop: 8,
									padding: 10,
									borderRadius: 8,
									background: "#f9fafb",
									border: "1px solid #e5e7eb",
									fontSize: 12,
									lineHeight: 1.45,
									overflow: "auto",
								}}
							>
								{JSON.stringify(entry.error.details, null, 2)}
							</pre>
						</details>
					)}
				</div>
			</div>
		</div>
	);
}
