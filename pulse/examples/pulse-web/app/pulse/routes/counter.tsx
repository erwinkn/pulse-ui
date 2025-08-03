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
        "Counter Example"
      ]
    },
    {
      "tag": "div",
      "children": [
        {
          "tag": "button",
          "children": [
            "-"
          ],
          "props": {
            "onClick": "$$callback:1.0.onClick"
          }
        },
        {
          "tag": "span",
          "props": {
            "style": {
              "margin": "0 20px",
              "fontSize": "18px"
            }
          },
          "children": [
            " Counter: 4 "
          ]
        },
        {
          "tag": "button",
          "children": [
            "+"
          ],
          "props": {
            "onClick": "$$callback:1.2.onClick"
          }
        }
      ]
    },
    {
      "tag": "p",
      "children": [
        "Note: This is a simple demo. State management would require additional implementation."
      ]
    },
    {
      "tag": "p",
      "children": [
        {
          "tag": "$$Link",
          "props": {
            "to": "/"
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
