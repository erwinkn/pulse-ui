export interface RouteNode {
	path: string;
	component?: () => Promise<{ default: React.ComponentType<any> }>;
	children?: RouteNode[];
}

export const routes: RouteNode[] = [
	{
		path: "",
		component: () => import("pulse/routes/index.jsx").then((m) => ({ default: m.default })),
	},
];
