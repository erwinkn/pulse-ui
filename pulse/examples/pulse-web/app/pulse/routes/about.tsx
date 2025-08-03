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
        "About Pulse UI"
      ]
    },
    {
      "tag": "p",
      "children": [
        "Pulse UI bridges Python and React, allowing you to:"
      ]
    },
    {
      "tag": "ul",
      "children": [
        {
          "tag": "li",
          "props": {
            "key": "feature-1"
          },
          "children": [
            "Define UI components in Python"
          ]
        },
        {
          "tag": "li",
          "props": {
            "key": "feature-2"
          },
          "children": [
            "Handle events with Python functions"
          ]
        },
        {
          "tag": "li",
          "props": {
            "key": "feature-3"
          },
          "children": [
            "Generate TypeScript automatically"
          ]
        },
        {
          "tag": "li",
          "props": {
            "key": "feature-4"
          },
          "children": [
            "Build reactive web applications"
          ]
        }
      ]
    },
    {
      "tag": "p",
      "children": [
        {
          "tag": "a",
          "props": {
            "href": "/"
          },
          "children": [
            "\u2190 Back to Home"
          ]
        }
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
