/** Get the top and bottom bounds of an element, accounting for padding. */
export function getElementBounds(element: HTMLElement): { top: number; bottom: number } {
	const styles = getComputedStyle(element);
	return {
		top: element.offsetTop + parseFloat(styles.paddingTop),
		bottom: element.offsetTop + element.clientHeight - parseFloat(styles.paddingBottom),
	};
}
