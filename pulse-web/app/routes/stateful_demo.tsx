import { ReactiveUIContainer } from "../ui-tree";
import { ComponentRegistryProvider } from "../ui-tree/component-registry";
import type { ComponentType } from "react";

// Component imports
import { ColorBox } from "../ui-tree/demo-components";
import { Counter } from "../ui-tree/demo-components";
import { ProgressBar } from "../ui-tree/demo-components";

// Component registry
const componentRegistry: Record<string, ComponentType<any>> = {
  "color-box": ColorBox,
  "counter": Counter,
  "progress-bar": ProgressBar,
};

const initialTree = {
  "id": "py_890320",
  "tag": "div",
  "props": {},
  "children": [
    {
      "id": "py_755568",
      "tag": "div",
      "props": {
        "className": "max-w-4xl mx-auto py-8 px-4"
      },
      "children": [
        {
          "id": "py_849558",
          "tag": "h1",
          "props": {},
          "children": [
            "\ud83c\udfa8 Stateful Components Demo"
          ]
        },
        {
          "id": "py_267984",
          "tag": "p",
          "props": {},
          "children": [
            "This page demonstrates React components with internal state that render server-provided children."
          ]
        },
        {
          "id": "py_741955",
          "tag": "div",
          "props": {
            "className": "space-y-6"
          },
          "children": [
            {
              "id": "py_129681",
              "tag": "$$color-box",
              "props": {
                "title": "Color Switcher #1",
                "initialColor": "blue"
              },
              "children": [
                {
                  "id": "py_517547",
                  "tag": "h3",
                  "props": {},
                  "children": [
                    "Server-Rendered Content Inside Stateful Component"
                  ]
                },
                {
                  "id": "py_244567",
                  "tag": "p",
                  "props": {},
                  "children": [
                    "This content was generated on the Python server, but it's rendered inside a React component that has its own state (the background color)."
                  ]
                },
                {
                  "id": "py_775241",
                  "tag": "$$counter",
                  "props": {
                    "count": 42,
                    "label": "Nested Counter"
                  },
                  "children": [
                    "This counter is nested inside the stateful ColorBox!"
                  ]
                }
              ]
            },
            {
              "id": "py_867131",
              "tag": "$$color-box",
              "props": {
                "title": "Color Switcher #2",
                "initialColor": "red"
              },
              "children": [
                {
                  "id": "py_640949",
                  "tag": "h3",
                  "props": {},
                  "children": [
                    "Another Example"
                  ]
                },
                {
                  "id": "py_337371",
                  "tag": "p",
                  "props": {},
                  "children": [
                    "Each ColorBox component maintains its own independent state."
                  ]
                },
                {
                  "id": "py_809824",
                  "tag": "ul",
                  "props": {},
                  "children": [
                    {
                      "id": "py_966926",
                      "tag": "li",
                      "props": {},
                      "children": [
                        "\u2713 Independent state management"
                      ]
                    },
                    {
                      "id": "py_848576",
                      "tag": "li",
                      "props": {},
                      "children": [
                        "\u2713 Server-rendered children"
                      ]
                    },
                    {
                      "id": "py_216470",
                      "tag": "li",
                      "props": {},
                      "children": [
                        "\u2713 Seamless hydration"
                      ]
                    }
                  ]
                }
              ]
            },
            {
              "id": "py_360162",
              "tag": "$$color-box",
              "props": {
                "title": "Progress Tracker",
                "initialColor": "purple"
              },
              "children": [
                {
                  "id": "py_269359",
                  "tag": "p",
                  "props": {},
                  "children": [
                    "This ColorBox contains a progress bar component:"
                  ]
                },
                {
                  "id": "py_994804",
                  "tag": "$$progress-bar",
                  "props": {
                    "value": 75,
                    "max": 100,
                    "label": "Task Progress",
                    "color": "green"
                  },
                  "children": []
                },
                {
                  "id": "py_657188",
                  "tag": "p",
                  "props": {},
                  "children": [
                    "The progress bar is also a React component, demonstrating nested component composition."
                  ]
                }
              ]
            }
          ]
        },
        {
          "id": "py_895154",
          "tag": "div",
          "props": {
            "className": "mt-8 p-6 bg-blue-50 border border-blue-200 rounded-lg"
          },
          "children": [
            {
              "id": "py_832904",
              "tag": "h2",
              "props": {},
              "children": [
                "\ud83d\udca1 Key Insights"
              ]
            },
            {
              "id": "py_383590",
              "tag": "ul",
              "props": {
                "className": "mt-4 space-y-2"
              },
              "children": [
                {
                  "id": "py_394140",
                  "tag": "li",
                  "props": {},
                  "children": [
                    "\ud83d\udd04 ",
                    {
                      "id": "py_628292",
                      "tag": "strong",
                      "props": {},
                      "children": [
                        "Hybrid Rendering"
                      ]
                    },
                    ": Server generates initial structure, React handles interactivity"
                  ]
                },
                {
                  "id": "py_575638",
                  "tag": "li",
                  "props": {},
                  "children": [
                    "\ud83e\udde9 ",
                    {
                      "id": "py_274808",
                      "tag": "strong",
                      "props": {},
                      "children": [
                        "Component Composition"
                      ]
                    },
                    ": Server-rendered children work seamlessly with stateful components"
                  ]
                },
                {
                  "id": "py_162110",
                  "tag": "li",
                  "props": {},
                  "children": [
                    "\u26a1 ",
                    {
                      "id": "py_279277",
                      "tag": "strong",
                      "props": {},
                      "children": [
                        "Performance"
                      ]
                    },
                    ": Fast initial render from server, enhanced with client-side capabilities"
                  ]
                },
                {
                  "id": "py_292743",
                  "tag": "li",
                  "props": {},
                  "children": [
                    "\ud83c\udfaf ",
                    {
                      "id": "py_930284",
                      "tag": "strong",
                      "props": {},
                      "children": [
                        "Flexibility"
                      ]
                    },
                    ": Choose the right tool for each part of your UI"
                  ]
                }
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
