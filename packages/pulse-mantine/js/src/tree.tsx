import { useEffect, useMemo, type ComponentPropsWithoutRef } from "react";
import { Tree as MantineTree, useTree } from "@mantine/core";
import { usePulseChannel } from "pulse-ui-client";

type ExpandedState = Record<string, boolean>;

export interface PulseTreeProps
  extends Omit<ComponentPropsWithoutRef<typeof MantineTree>, "tree"> {
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

export function Tree({
  channelId,
  initialExpandedState,
  initialSelectedState,
  initialCheckedState,
  multiple,
  autoSync = true,
  ...rest
}: PulseTreeProps) {
  const channel = channelId ? usePulseChannel(channelId) : undefined;

  // Create controller with initial state and wire auto-sync callbacks
  const tree = useTree({
    initialExpandedState: initialExpandedState ?? {},
    initialSelectedState,
    initialCheckedState,
    multiple,
    onNodeExpand: (value: string) => {
      if (!autoSync || !channel) return;
      channel.emit("nodeExpand", { value });
    },
    onNodeCollapse: (value: string) => {
      if (!autoSync || !channel) return;
      channel.emit("nodeCollapse", { value });
    },
  } as any);

  // Server -> client imperative API
  useEffect(() => {
    if (!channel) return;
    const cleanups = [
      channel.on("toggleExpanded", (payload: { value: string }) => {
        if (!payload) return;
        tree.toggleExpanded(payload.value);
      }),
      channel.on("expand", (payload: { value: string }) => {
        if (!payload) return;
        tree.expand(payload.value);
      }),
      channel.on("collapse", (payload: { value: string }) => {
        if (!payload) return;
        tree.collapse(payload.value);
      }),
      channel.on("expandAllNodes", () => {
        tree.expandAllNodes();
      }),
      channel.on("collapseAllNodes", () => {
        tree.collapseAllNodes();
      }),
      channel.on(
        "setExpandedState",
        (payload: { expandedState: ExpandedState }) => {
          if (!payload) return;
          tree.setExpandedState(payload.expandedState ?? {});
        }
      ),
      channel.on("getCheckedNodes", () => tree.getCheckedNodes()),
      channel.on("getExpandedState", () => tree.expandedState),
      // Selection API
      channel.on("toggleSelected", (payload: { value: string }) => {
        if (!payload) return;
        tree.toggleSelected(payload.value);
      }),
      channel.on("select", (payload: { value: string }) => {
        if (!payload) return;
        tree.select(payload.value);
      }),
      channel.on("deselect", (payload: { value: string }) => {
        if (!payload) return;
        tree.deselect(payload.value);
      }),
      channel.on("clearSelected", () => {
        tree.clearSelected();
      }),
      channel.on("setSelectedState", (payload: { selectedState: string[] }) => {
        if (!payload) return;
        tree.setSelectedState(payload.selectedState ?? []);
      }),
      channel.on("getSelectedState", () => tree.selectedState),
      channel.on("getAnchorNode", () => tree.anchorNode),
      // Hover API
      channel.on("setHoveredNode", (payload: { value?: string | null }) => {
        tree.setHoveredNode(payload?.value ?? null);
      }),
      channel.on("getHoveredNode", () => tree.hoveredNode),
      // Checked API
      channel.on("checkNode", (payload: { value: string }) => {
        if (!payload) return;
        tree.checkNode(payload.value);
      }),
      channel.on("uncheckNode", (payload: { value: string }) => {
        if (!payload) return;
        tree.uncheckNode(payload.value);
      }),
      channel.on("checkAllNodes", () => tree.checkAllNodes()),
      channel.on("uncheckAllNodes", () => tree.uncheckAllNodes()),
      channel.on("setCheckedState", (payload: { checkedState: string[] }) => {
        if (!payload) return;
        tree.setCheckedState(payload.checkedState ?? []);
      }),
      channel.on("getCheckedState", () => tree.checkedState),
      channel.on("isNodeChecked", (payload: { value: string }) =>
        tree.isNodeChecked(payload?.value)
      ),
      channel.on("isNodeIndeterminate", (payload: { value: string }) =>
        tree.isNodeIndeterminate(payload?.value)
      ),
    ];
    return () => {
      for (const dispose of cleanups) dispose();
    };
  }, [channel, tree]);

  return <MantineTree {...(rest as any)} tree={tree as any} />;
}
