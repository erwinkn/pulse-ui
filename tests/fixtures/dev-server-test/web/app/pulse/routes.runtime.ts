import type { RouteObject } from "react-router";

export type RRRouteObject = RouteObject & {
	id: string;
	uniquePath?: string;
	children?: RRRouteObject[];
	file: string;
};

export const rrPulseRouteTree = [
	{
		id: "/",
		uniquePath: "/",
		index: true,
		file: "pulse/routes/index.jsx",
	},
] satisfies RRRouteObject[];
