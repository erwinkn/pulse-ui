import { useState, useCallback, useMemo } from "react";
import type { UINode, UIUpdatePayload } from "./tree";
import { applyUpdates } from "./update-utils";

export interface UseReactiveUITreeOptions {
  initialTree: UINode;
}

export interface UseReactiveUITreeReturn {
  tree: UINode;
  applyUpdate: (update: UIUpdatePayload) => void;
  applyBatchUpdates: (updates: UIUpdatePayload[]) => void;
  setTree: (tree: UINode) => void;
}

export function useReactiveUITree({
  initialTree,
}: UseReactiveUITreeOptions): UseReactiveUITreeReturn {
  const [tree, setTree] = useState<UINode>(initialTree);

  const applyUpdate = useCallback((update: UIUpdatePayload) => {
    setTree((currentTree) => applyUpdates(currentTree, [update]));
  }, []);

  const applyBatchUpdates = useCallback((updates: UIUpdatePayload[]) => {
    console.log("Applying updates", updates)
    setTree((currentTree) => applyUpdates(currentTree, updates));
  }, []);

  return useMemo(
    () => ({
      tree,
      applyUpdate,
      applyBatchUpdates,
      setTree,
    }),
    [tree, applyUpdate, applyBatchUpdates, setTree]
  );
}
