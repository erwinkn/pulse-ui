import { ReactiveUIContainer } from "../ui-tree";
import { ComponentRegistryProvider } from "../ui-tree/component-registry";
import type { ComponentType } from "react";

// Component imports
import { UserCard } from "../ui-tree/demo-components";

// Component registry
const componentRegistry: Record<string, ComponentType<any>> = {
  "user-card": UserCard,
};

const initialTree = {
  "id": "py_539555",
  "tag": "div",
  "props": {},
  "children": [
    {
      "id": "py_570342",
      "tag": "div",
      "props": {
        "className": "max-w-4xl mx-auto py-8 px-4"
      },
      "children": [
        {
          "id": "py_492665",
          "tag": "h1",
          "props": {},
          "children": [
            "\ud83d\udcca API Data Example"
          ]
        },
        {
          "id": "py_418013",
          "tag": "p",
          "props": {},
          "children": [
            "This route demonstrates how you might render data from an API:"
          ]
        },
        {
          "id": "py_795292",
          "tag": "div",
          "props": {
            "className": "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
          },
          "children": [
            {
              "id": "py_555358",
              "tag": "$$user-card",
              "props": {
                "name": "John Doe",
                "email": "john@example.com",
                "avatar": "https://i.pravatar.cc/150?u=john@example.com"
              },
              "children": []
            },
            {
              "id": "py_578624",
              "tag": "$$user-card",
              "props": {
                "name": "Jane Smith",
                "email": "jane@example.com",
                "avatar": "https://i.pravatar.cc/150?u=jane@example.com"
              },
              "children": []
            },
            {
              "id": "py_722571",
              "tag": "$$user-card",
              "props": {
                "name": "Mike Johnson",
                "email": "mike@example.com",
                "avatar": "https://i.pravatar.cc/150?u=mike@example.com"
              },
              "children": []
            }
          ]
        }
      ]
    }
  ]
};

export default function RouteComponent() {
  return (
    <ComponentRegistryProvider registry={componentRegistry}>
      <ReactiveUIContainer
        initialTree={initialTree}
        transport={null} // Will be set up later for WebSocket connection
      />
    </ComponentRegistryProvider>
  );
}
