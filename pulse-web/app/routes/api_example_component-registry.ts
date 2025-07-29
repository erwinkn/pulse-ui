import type { ComponentType } from "react";
import { UserCard } from "../ui-tree/demo-components";

export const componentRegistry: Record<string, ComponentType<any>> = {
  "user-card": UserCard,
};
