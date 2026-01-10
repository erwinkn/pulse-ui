export type PulseRouteNode = {
	id: string;
	uniquePath?: string;
	path?: string;
	index?: boolean;
	file: string;
	children?: PulseRouteNode[];
};

export const pulsePulseRouteTree = [
	{
		id: "/",
		uniquePath: "/",
		path: "/",
		file: "pulse/routes/index.jsx",
	},
] satisfies PulseRouteNode[];
