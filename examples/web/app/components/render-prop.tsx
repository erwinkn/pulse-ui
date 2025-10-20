import type { ReactElement } from "react";

interface RenderPropComponentProps {
	left?: ReactElement;
	right?: ReactElement;
}
export function RenderPropComponent({
	left,
	right,
	children,
}: React.PropsWithChildren<RenderPropComponentProps>) {
	return (
		<>
			{left}
			{children}
			{right}
		</>
	);
}
