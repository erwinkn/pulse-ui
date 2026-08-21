import { Tree as MantineTree, useTree } from "@mantine/core";
import { useChannel } from "pulse-ui-client";
import { type ComponentPropsWithoutRef, useEffect, useLayoutEffect, useRef } from "react";

type ExpandedState = Record<string, boolean>;

export interface PulseTreeProps extends Omit<ComponentPropsWithoutRef<typeof MantineTree>, "tree"> {
	channelId?: string;
	/** Initial expanded state for useTree; seeded from server */
	initialExpandedState?: ExpandedState;
	/** Initial selected state of nodes */
	initialSelectedState?: string[];
	/** Initial checked state of nodes */
	initialCheckedState?: string[];
	/** Determines whether multiple node can be selected at a time */
	multiple?: boolean;
	/** Enable client->server auto sync on expand/collapse (default: true) */
	autoSync?: boolean;
}

type ConnectedTreeProps = PulseTreeProps & {
	channelId: string;
};

export function Tree({
	channelId,
	...props
}: PulseTreeProps) {
	if (!channelId) {
		return <PlainTree {...props} />;
	}

	return <ConnectedTree channelId={channelId} {...props} />;
}

function PlainTree({
	initialExpandedState,
	initialSelectedState,
	initialCheckedState,
	multiple,
	...rest
}: PulseTreeProps) {
	const tree = useTree({
		initialExpandedState: initialExpandedState ?? {},
		initialSelectedState,
		initialCheckedState,
		multiple,
	} as any);

	return <MantineTree {...(rest as any)} tree={tree as any} />;
}

function ConnectedTree({
	channelId,
	initialExpandedState,
	initialSelectedState,
	initialCheckedState,
	multiple,
	autoSync = true,
	...rest
}: ConnectedTreeProps) {
	const channel = useChannel(channelId);
	const channelRef = useRef(channel);
	useLayoutEffect(() => {
		channelRef.current = channel;
	}, [channel]);

	// Create controller with initial state and wire auto-sync callbacks
	const tree = useTree({
		initialExpandedState: initialExpandedState ?? {},
		initialSelectedState,
		initialCheckedState,
		multiple,
		onNodeExpand: (value: string) => {
			if (!autoSync) return;
			channelRef.current?.emit("nodeExpand", { value });
		},
		onNodeCollapse: (value: string) => {
			if (!autoSync) return;
			channelRef.current?.emit("nodeCollapse", { value });
		},
	} as any);
	const treeRef = useRef(tree);
	useLayoutEffect(() => {
		treeRef.current = tree;
	});

	// Server -> client imperative API
	useEffect(() => {
		const cleanups = [
			channel.on("toggleExpanded", (payload: { value: string }) => {
				if (!payload) return;
				treeRef.current.toggleExpanded(payload.value);
			}),
			channel.on("expand", (payload: { value: string }) => {
				if (!payload) return;
				treeRef.current.expand(payload.value);
			}),
			channel.on("collapse", (payload: { value: string }) => {
				if (!payload) return;
				treeRef.current.collapse(payload.value);
			}),
			channel.on("expandAllNodes", () => treeRef.current.expandAllNodes()),
			channel.on("collapseAllNodes", () => treeRef.current.collapseAllNodes()),
			channel.on("setExpandedState", (payload: { expandedState: ExpandedState }) => {
				if (!payload) return;
				treeRef.current.setExpandedState(payload.expandedState ?? {});
			}),
			channel.on("getCheckedNodes", () => treeRef.current.getCheckedNodes()),
			channel.on("getExpandedState", () => treeRef.current.expandedState),
			// Selection API
			channel.on("toggleSelected", (payload: { value: string }) => {
				if (!payload) return;
				treeRef.current.toggleSelected(payload.value);
			}),
			channel.on("select", (payload: { value: string }) => {
				if (!payload) return;
				treeRef.current.select(payload.value);
			}),
			channel.on("deselect", (payload: { value: string }) => {
				if (!payload) return;
				treeRef.current.deselect(payload.value);
			}),
			channel.on("clearSelected", () => treeRef.current.clearSelected()),
			channel.on("setSelectedState", (payload: { selectedState: string[] }) => {
				if (!payload) return;
				treeRef.current.setSelectedState(payload.selectedState ?? []);
			}),
			channel.on("getSelectedState", () => treeRef.current.selectedState),
			channel.on("getAnchorNode", () => treeRef.current.anchorNode),
			// Hover API
			channel.on("setHoveredNode", (payload: { value?: string | null }) => {
				treeRef.current.setHoveredNode(payload?.value ?? null);
			}),
			channel.on("getHoveredNode", () => treeRef.current.hoveredNode),
			// Checked API
			channel.on("checkNode", (payload: { value: string }) => {
				if (!payload) return;
				treeRef.current.checkNode(payload.value);
			}),
			channel.on("uncheckNode", (payload: { value: string }) => {
				if (!payload) return;
				treeRef.current.uncheckNode(payload.value);
			}),
			channel.on("checkAllNodes", () => treeRef.current.checkAllNodes()),
			channel.on("uncheckAllNodes", () => treeRef.current.uncheckAllNodes()),
			channel.on("setCheckedState", (payload: { checkedState: string[] }) => {
				if (!payload) return;
				treeRef.current.setCheckedState(payload.checkedState ?? []);
			}),
			channel.on("getCheckedState", () => treeRef.current.checkedState),
			channel.on("isNodeChecked", (payload: { value: string }) =>
				treeRef.current.isNodeChecked(payload?.value),
			),
			channel.on("isNodeIndeterminate", (payload: { value: string }) =>
				treeRef.current.isNodeIndeterminate(payload?.value),
			),
		];
		return () => {
			for (const dispose of cleanups) dispose();
		};
	}, [channel]);

	return <MantineTree {...(rest as any)} tree={tree as any} />;
}
