import { ReactiveUIContainer } from "../ui-tree";
import { ComponentRegistryProvider } from "../ui-tree/component-registry";
import type { ComponentType } from "react";

// No components needed for this route
const componentRegistry: Record<string, ComponentType<any>> = {};

const initialTree = {
  "id": "py_801142",
  "tag": "div",
  "props": {},
  "children": [
    {
      "id": "py_130917",
      "tag": "div",
      "props": {
        "className": "max-w-4xl mx-auto py-8 px-4"
      },
      "children": [
        {
          "id": "py_220934",
          "tag": "h1",
          "props": {
            "className": "text-4xl font-bold text-gray-900 mb-2"
          },
          "children": [
            "\ud83d\ude80 Pulse UI Demo"
          ]
        },
        {
          "id": "py_976441",
          "tag": "p",
          "props": {
            "className": "text-xl text-gray-600 mb-8"
          },
          "children": [
            "Server-rendered React components with Python integration"
          ]
        },
        {
          "id": "py_253131",
          "tag": "div",
          "props": {
            "className": "grid grid-cols-1 md:grid-cols-2 gap-6"
          },
          "children": [
            {
              "id": "py_156812",
              "tag": "div",
              "props": {
                "className": "bg-white border border-gray-200 rounded-lg p-6 shadow-sm hover:shadow-md transition-shadow"
              },
              "children": [
                {
                  "id": "py_942731",
                  "tag": "h3",
                  "props": {
                    "className": "text-xl font-semibold text-gray-900 mb-3"
                  },
                  "children": [
                    "\ud83d\udd27 Server-Generated Demo"
                  ]
                },
                {
                  "id": "py_829842",
                  "tag": "p",
                  "props": {
                    "className": "text-gray-600 mb-4"
                  },
                  "children": [
                    "Complex route with nested React components, server-rendered children, and stateful interactions."
                  ]
                },
                {
                  "id": "py_464918",
                  "tag": "ul",
                  "props": {
                    "className": "text-sm text-gray-500 mb-4 space-y-1"
                  },
                  "children": [
                    {
                      "id": "py_366702",
                      "tag": "li",
                      "props": {},
                      "children": [
                        "\u2713 Nested React components"
                      ]
                    },
                    {
                      "id": "py_114990",
                      "tag": "li",
                      "props": {},
                      "children": [
                        "\u2713 Server-side props"
                      ]
                    },
                    {
                      "id": "py_501547",
                      "tag": "li",
                      "props": {},
                      "children": [
                        "\u2713 Stateful ColorBox component"
                      ]
                    },
                    {
                      "id": "py_452764",
                      "tag": "li",
                      "props": {},
                      "children": [
                        "\u2713 Mixed content types"
                      ]
                    }
                  ]
                },
                {
                  "id": "py_531612",
                  "tag": "a",
                  "props": {
                    "href": "/server-demo",
                    "className": "inline-block bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 transition-colors"
                  },
                  "children": [
                    "View Demo \u2192"
                  ]
                }
              ]
            },
            {
              "id": "py_524166",
              "tag": "div",
              "props": {
                "className": "bg-white border border-gray-200 rounded-lg p-6 shadow-sm hover:shadow-md transition-shadow"
              },
              "children": [
                {
                  "id": "py_265246",
                  "tag": "h3",
                  "props": {
                    "className": "text-xl font-semibold text-gray-900 mb-3"
                  },
                  "children": [
                    "\ud83d\udcca API Data Example"
                  ]
                },
                {
                  "id": "py_811967",
                  "tag": "p",
                  "props": {
                    "className": "text-gray-600 mb-4"
                  },
                  "children": [
                    "Demonstrates rendering dynamic data from API calls with React components."
                  ]
                },
                {
                  "id": "py_591652",
                  "tag": "ul",
                  "props": {
                    "className": "text-sm text-gray-500 mb-4 space-y-1"
                  },
                  "children": [
                    {
                      "id": "py_494207",
                      "tag": "li",
                      "props": {},
                      "children": [
                        "\u2713 Dynamic data rendering"
                      ]
                    },
                    {
                      "id": "py_693354",
                      "tag": "li",
                      "props": {},
                      "children": [
                        "\u2713 User card components"
                      ]
                    },
                    {
                      "id": "py_631237",
                      "tag": "li",
                      "props": {},
                      "children": [
                        "\u2713 List iteration in Python"
                      ]
                    },
                    {
                      "id": "py_522486",
                      "tag": "li",
                      "props": {},
                      "children": [
                        "\u2713 Avatar integration"
                      ]
                    }
                  ]
                },
                {
                  "id": "py_165880",
                  "tag": "a",
                  "props": {
                    "href": "/api-example",
                    "className": "inline-block bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700 transition-colors"
                  },
                  "children": [
                    "View Demo \u2192"
                  ]
                }
              ]
            },
            {
              "id": "py_354755",
              "tag": "div",
              "props": {
                "className": "bg-white border border-gray-200 rounded-lg p-6 shadow-sm hover:shadow-md transition-shadow"
              },
              "children": [
                {
                  "id": "py_577831",
                  "tag": "h3",
                  "props": {
                    "className": "text-xl font-semibold text-gray-900 mb-3"
                  },
                  "children": [
                    "\ud83c\udfaf Simple Static Route"
                  ]
                },
                {
                  "id": "py_861546",
                  "tag": "p",
                  "props": {
                    "className": "text-gray-600 mb-4"
                  },
                  "children": [
                    "Pure HTML elements without React components, showing the flexibility of the system."
                  ]
                },
                {
                  "id": "py_737571",
                  "tag": "ul",
                  "props": {
                    "className": "text-sm text-gray-500 mb-4 space-y-1"
                  },
                  "children": [
                    {
                      "id": "py_902843",
                      "tag": "li",
                      "props": {},
                      "children": [
                        "\u2713 HTML-only content"
                      ]
                    },
                    {
                      "id": "py_421993",
                      "tag": "li",
                      "props": {},
                      "children": [
                        "\u2713 No React dependencies"
                      ]
                    },
                    {
                      "id": "py_893785",
                      "tag": "li",
                      "props": {},
                      "children": [
                        "\u2713 Fast server rendering"
                      ]
                    },
                    {
                      "id": "py_628169",
                      "tag": "li",
                      "props": {},
                      "children": [
                        "\u2713 Static optimization"
                      ]
                    }
                  ]
                },
                {
                  "id": "py_164289",
                  "tag": "a",
                  "props": {
                    "href": "/simple",
                    "className": "inline-block bg-gray-600 text-white px-4 py-2 rounded hover:bg-gray-700 transition-colors"
                  },
                  "children": [
                    "View Demo \u2192"
                  ]
                }
              ]
            },
            {
              "id": "py_264535",
              "tag": "div",
              "props": {
                "className": "bg-white border border-gray-200 rounded-lg p-6 shadow-sm hover:shadow-md transition-shadow"
              },
              "children": [
                {
                  "id": "py_964836",
                  "tag": "h3",
                  "props": {
                    "className": "text-xl font-semibold text-gray-900 mb-3"
                  },
                  "children": [
                    "\ud83c\udfa8 Stateful Components"
                  ]
                },
                {
                  "id": "py_879096",
                  "tag": "p",
                  "props": {
                    "className": "text-gray-600 mb-4"
                  },
                  "children": [
                    "React components with internal state that render server-provided children."
                  ]
                },
                {
                  "id": "py_654097",
                  "tag": "ul",
                  "props": {
                    "className": "text-sm text-gray-500 mb-4 space-y-1"
                  },
                  "children": [
                    {
                      "id": "py_625423",
                      "tag": "li",
                      "props": {},
                      "children": [
                        "\u2713 Client-side state management"
                      ]
                    },
                    {
                      "id": "py_315519",
                      "tag": "li",
                      "props": {},
                      "children": [
                        "\u2713 Server-rendered children"
                      ]
                    },
                    {
                      "id": "py_609983",
                      "tag": "li",
                      "props": {},
                      "children": [
                        "\u2713 Interactive color switching"
                      ]
                    },
                    {
                      "id": "py_800210",
                      "tag": "li",
                      "props": {},
                      "children": [
                        "\u2713 Hybrid rendering approach"
                      ]
                    }
                  ]
                },
                {
                  "id": "py_136872",
                  "tag": "a",
                  "props": {
                    "href": "/stateful-demo",
                    "className": "inline-block bg-purple-600 text-white px-4 py-2 rounded hover:bg-purple-700 transition-colors"
                  },
                  "children": [
                    "View Demo \u2192"
                  ]
                }
              ]
            }
          ]
        },
        {
          "id": "py_159852",
          "tag": "div",
          "props": {
            "className": "mt-12 p-6 bg-gray-50 rounded-lg"
          },
          "children": [
            {
              "id": "py_834511",
              "tag": "h2",
              "props": {
                "className": "text-2xl font-semibold text-gray-900 mb-4"
              },
              "children": [
                "\ud83d\udee0\ufe0f How It Works"
              ]
            },
            {
              "id": "py_581160",
              "tag": "div",
              "props": {
                "className": "grid grid-cols-1 md:grid-cols-3 gap-4 text-sm"
              },
              "children": [
                {
                  "id": "py_914970",
                  "tag": "div",
                  "props": {},
                  "children": [
                    {
                      "id": "py_506738",
                      "tag": "strong",
                      "props": {
                        "className": "text-gray-900"
                      },
                      "children": [
                        "1. Python Definition"
                      ]
                    },
                    {
                      "id": "py_454319",
                      "tag": "p",
                      "props": {
                        "className": "text-gray-600 mt-1"
                      },
                      "children": [
                        "Define React components and routes using Python syntax with the ",
                        {
                          "id": "py_384020",
                          "tag": "code",
                          "props": {},
                          "children": [
                            "pulse.html"
                          ]
                        },
                        " library."
                      ]
                    }
                  ]
                },
                {
                  "id": "py_512530",
                  "tag": "div",
                  "props": {},
                  "children": [
                    {
                      "id": "py_290331",
                      "tag": "strong",
                      "props": {
                        "className": "text-gray-900"
                      },
                      "children": [
                        "2. TypeScript Generation"
                      ]
                    },
                    {
                      "id": "py_863199",
                      "tag": "p",
                      "props": {
                        "className": "text-gray-600 mt-1"
                      },
                      "children": [
                        "Generate TypeScript files with component registries and UI trees automatically."
                      ]
                    }
                  ]
                },
                {
                  "id": "py_824618",
                  "tag": "div",
                  "props": {},
                  "children": [
                    {
                      "id": "py_962098",
                      "tag": "strong",
                      "props": {
                        "className": "text-gray-900"
                      },
                      "children": [
                        "3. React Rendering"
                      ]
                    },
                    {
                      "id": "py_617274",
                      "tag": "p",
                      "props": {
                        "className": "text-gray-600 mt-1"
                      },
                      "children": [
                        "Render with full React capabilities including state, effects, and server-rendered children."
                      ]
                    }
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
