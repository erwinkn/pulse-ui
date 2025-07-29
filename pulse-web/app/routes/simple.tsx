import { ReactiveUIContainer } from "../ui-tree";
import { ComponentRegistryProvider } from "../ui-tree/component-registry";
import type { ComponentType } from "react";

// No components needed for this route
const componentRegistry: Record<string, ComponentType<any>> = {};

const initialTree = {
  "id": "py_667389",
  "tag": "div",
  "props": {},
  "children": [
    {
      "id": "py_517186",
      "tag": "div",
      "props": {
        "className": "max-w-4xl mx-auto py-8 px-4"
      },
      "children": [
        {
          "id": "py_768433",
          "tag": "h1",
          "props": {},
          "children": [
            "\ud83c\udfaf Simple Static Route"
          ]
        },
        {
          "id": "py_484782",
          "tag": "p",
          "props": {},
          "children": [
            "This route uses only HTML elements, no React components."
          ]
        },
        {
          "id": "py_441194",
          "tag": "p",
          "props": {},
          "children": [
            "It demonstrates that you can mix static and dynamic content."
          ]
        },
        {
          "id": "py_237733",
          "tag": "h2",
          "props": {},
          "children": [
            "Pure HTML Elements"
          ]
        },
        {
          "id": "py_973556",
          "tag": "ul",
          "props": {},
          "children": [
            {
              "id": "py_765815",
              "tag": "li",
              "props": {},
              "children": [
                "This is a regular HTML list item"
              ]
            },
            {
              "id": "py_582261",
              "tag": "li",
              "props": {},
              "children": [
                "No React components involved"
              ]
            },
            {
              "id": "py_894805",
              "tag": "li",
              "props": {},
              "children": [
                "Fast server-side rendering"
              ]
            },
            {
              "id": "py_479845",
              "tag": "li",
              "props": {},
              "children": [
                "Perfect for static content"
              ]
            }
          ]
        },
        {
          "id": "py_547238",
          "tag": "button",
          "props": {},
          "children": [
            "This is just an HTML button"
          ]
        },
        {
          "id": "py_928858",
          "tag": "div",
          "props": {
            "className": "mt-6 p-4 bg-yellow-50 border border-yellow-200 rounded"
          },
          "children": [
            {
              "id": "py_768187",
              "tag": "p",
              "props": {},
              "children": [
                {
                  "id": "py_902593",
                  "tag": "strong",
                  "props": {},
                  "children": [
                    "Note: "
                  ]
                },
                "This demonstrates the flexibility of the Pulse UI system. ",
                "You can choose to use React components where you need interactivity, ",
                "and plain HTML where you don't."
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
