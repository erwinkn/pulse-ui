import { PulseView } from "~/pulse-lib/pulse";
import type { VDOM, ComponentRegistry } from "~/pulse-lib/vdom";

// Component imports
import { Link } from "react-router";
import { Outlet } from "react-router";

// Component registry
const externalComponents: ComponentRegistry = {
  "Link": Link,
  "Outlet": Outlet,
};

// The initial VDOM is bootstrapped from the server
const initialVDOM: VDOM = {
  "tag": "div",
  "children": [
    {
      "tag": "h1",
      "children": [
        "Welcome to Pulse UI!"
      ]
    },
    {
      "tag": "p",
      "children": [
        "This is a Python-powered web application."
      ]
    },
    {
      "tag": "button",
      "children": [
        "Click me!"
      ],
      "props": {
        "onClick": "$$callback:2.onClick"
      }
    },
    {
      "tag": "hr"
    },
    {
      "tag": "p",
      "children": [
        "Check the server logs to see the button click messages."
      ]
    }
  ]
};

export default function RouteComponent() {
  return (
    <PulseView
      initialVDOM={initialVDOM}
      externalComponents={externalComponents}
    />
  );
}
