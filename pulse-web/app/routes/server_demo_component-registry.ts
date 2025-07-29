import type { ComponentType } from "react";
import { Counter } from "../ui-tree/demo-components";
import { UserCard } from "../ui-tree/demo-components";
import { Button } from "../ui-tree/demo-components";
import { Card } from "../ui-tree/demo-components";

export const componentRegistry: Record<string, ComponentType<any>> = {
  "counter": Counter,
  "user-card": UserCard,
  "button": Button,
  "card": Card,
};
