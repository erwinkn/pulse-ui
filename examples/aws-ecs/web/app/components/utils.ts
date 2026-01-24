/**
 * Utility functions demonstrating JSExpr usage in the registry system.
 */

/**
 * Concatenates class names, filtering out falsy values.
 * This is a simple version of clsx/classnames.
 *
 * @example
 * cx("btn", isActive && "btn-active", className)
 */
export function cx(...classes: (string | boolean | null | undefined)[]): string {
	return classes.filter(Boolean).join(" ");
}

/**
 * Creates a greeting message - used to demonstrate JsFunction transpilation.
 * The Python @javascript decorator will transpile a Python function that
 * calls this, and the result can be used as both a callback and a value.
 */
export function formatGreeting(name: string, count: number): string {
	return `Hello, ${name}! You have ${count} new messages.`;
}

/**
 * A callback handler type for button clicks with metadata.
 */
export type ButtonClickHandler = (
	event: React.MouseEvent<HTMLButtonElement>,
	metadata: { timestamp: number },
) => void;

/**
 * Creates a click handler that logs with a prefix.
 * Demonstrates passing a JS function as a callback prop.
 */
export function createClickLogger(prefix: string): ButtonClickHandler {
	return (_event, metadata) => {
		console.log(`[${prefix}] Button clicked at ${metadata.timestamp}`);
	};
}
