import { ReactiveUIContainer } from "../ui-tree";
import { ComponentRegistryProvider } from "../ui-tree/component-registry";
import type { ComponentType } from "react";

// Component imports
import { Counter } from "../ui-tree/demo-components";
import { UserCard } from "../ui-tree/demo-components";
import { Button } from "../ui-tree/demo-components";
import { Card } from "../ui-tree/demo-components";
import { ColorBox } from "../ui-tree/demo-components";

// Component registry
const componentRegistry: Record<string, ComponentType<any>> = {
  "counter": Counter,
  "user-card": UserCard,
  "button": Button,
  "card": Card,
  "color-box": ColorBox,
};

const initialTree = {
  "id": "py_907221",
  "tag": "div",
  "props": {},
  "children": [
    {
      "id": "py_297220",
      "tag": "div",
      "props": {
        "className": "max-w-4xl mx-auto py-8 px-4"
      },
      "children": [
        {
          "id": "py_164314",
          "tag": "h1",
          "props": {},
          "children": [
            "\ud83d\udd27 Server-Generated Demo Route"
          ]
        },
        {
          "id": "py_974185",
          "tag": "p",
          "props": {},
          "children": [
            "This entire page was generated from Python code and rendered with React components."
          ]
        },
        {
          "id": "py_565608",
          "tag": "$$card",
          "props": {
            "title": "Welcome",
            "variant": "primary"
          },
          "children": [
            {
              "id": "py_731753",
              "tag": "p",
              "props": {},
              "children": [
                "This card component is a React component imported from the demo-components file."
              ]
            },
            {
              "id": "py_444082",
              "tag": "p",
              "props": {},
              "children": [
                "It can contain arbitrary children from the UI tree."
              ]
            }
          ]
        },
        {
          "id": "py_217407",
          "tag": "h2",
          "props": {},
          "children": [
            "Interactive Components"
          ]
        },
        {
          "id": "py_714863",
          "tag": "p",
          "props": {},
          "children": [
            "These components will be hydrated with React and become interactive:"
          ]
        },
        {
          "id": "py_280831",
          "tag": "$$counter",
          "props": {
            "count": 10,
            "label": "Server Counter"
          },
          "children": [
            "This counter was initialized with count=10 from the server."
          ]
        },
        {
          "id": "py_429026",
          "tag": "div",
          "props": {},
          "children": [
            {
              "id": "py_960825",
              "tag": "$$user-card",
              "props": {
                "name": "Alice Johnson",
                "email": "alice@example.com",
                "avatar": "https://i.pravatar.cc/150?img=1"
              },
              "children": []
            },
            {
              "id": "py_733247",
              "tag": "br",
              "props": {},
              "children": []
            },
            {
              "id": "py_867129",
              "tag": "$$user-card",
              "props": {
                "name": "Bob Smith",
                "email": "bob@example.com",
                "avatar": "https://i.pravatar.cc/150?img=2"
              },
              "children": []
            }
          ]
        },
        {
          "id": "py_358955",
          "tag": "h2",
          "props": {},
          "children": [
            "Stateful Component with Server-Rendered Children"
          ]
        },
        {
          "id": "py_720956",
          "tag": "p",
          "props": {},
          "children": [
            "This ColorBox component has internal React state but renders server-provided children:"
          ]
        },
        {
          "id": "py_793685",
          "tag": "$$color-box",
          "props": {
            "title": "Interactive Color Demo",
            "initialColor": "green"
          },
          "children": [
            {
              "id": "py_862667",
              "tag": "p",
              "props": {},
              "children": [
                "This content was generated on the server in Python."
              ]
            },
            {
              "id": "py_782197",
              "tag": "ul",
              "props": {},
              "children": [
                {
                  "id": "py_883752",
                  "tag": "li",
                  "props": {},
                  "children": [
                    "\u2713 Server-side rendering"
                  ]
                },
                {
                  "id": "py_956405",
                  "tag": "li",
                  "props": {},
                  "children": [
                    "\u2713 Client-side interactivity"
                  ]
                },
                {
                  "id": "py_405543",
                  "tag": "li",
                  "props": {},
                  "children": [
                    "\u2713 Seamless integration"
                  ]
                }
              ]
            },
            {
              "id": "py_562644",
              "tag": "strong",
              "props": {},
              "children": [
                "Click the color buttons above to change the background!"
              ]
            }
          ]
        },
        {
          "id": "py_636274",
          "tag": "h2",
          "props": {},
          "children": [
            "Nested Components"
          ]
        },
        {
          "id": "py_646579",
          "tag": "$$card",
          "props": {
            "title": "Nested Example"
          },
          "children": [
            {
              "id": "py_552714",
              "tag": "p",
              "props": {},
              "children": [
                "This card contains other React components:"
              ]
            },
            {
              "id": "py_523598",
              "tag": "$$button",
              "props": {
                "variant": "primary",
                "size": "large"
              },
              "children": [
                "Click me!"
              ]
            },
            {
              "id": "py_558056",
              "tag": "br",
              "props": {},
              "children": []
            },
            {
              "id": "py_425847",
              "tag": "br",
              "props": {},
              "children": []
            },
            {
              "id": "py_893418",
              "tag": "$$counter",
              "props": {
                "count": 5,
                "label": "Nested Counter"
              },
              "children": [
                "This counter is nested inside a card."
              ]
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
