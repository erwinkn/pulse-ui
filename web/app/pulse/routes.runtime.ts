import type { RouteObject } from "react-router";

export type RRRouteObject = RouteObject & {
  id: string;
  uniquePath?: string;
  children?: RRRouteObject[];
  file: string;
}

export const rrPulseRouteTree = [
  {
    id: "/<layout>",
    uniquePath: "/<layout>",
    file: "pulse/layouts/layout/_layout.tsx",
    children: [
      {
        id: "/",
        uniquePath: "/",
        index: true,
        file: "pulse/routes/index.jsx",
      }
    ,
      {
        id: "/about",
        uniquePath: "/about",
        path: "about",
        file: "pulse/routes/about.jsx",
      }
    ,
      {
        id: "/counter",
        uniquePath: "/counter",
        path: "counter",
        file: "pulse/routes/counter.jsx",
        children: [
          {
            id: "/counter/details",
            uniquePath: "/counter/details",
            path: "details",
            file: "pulse/routes/counter/details.jsx",
          }
        ],
      }
    ,
      {
        id: "/components",
        uniquePath: "/components",
        path: "components",
        file: "pulse/routes/components.jsx",
      }
    ,
      {
        id: "/datepicker",
        uniquePath: "/datepicker",
        path: "datepicker",
        file: "pulse/routes/datepicker.jsx",
      }
    ,
      {
        id: "/query",
        uniquePath: "/query",
        path: "query",
        file: "pulse/routes/query.jsx",
      }
    ,
      {
        id: "/async-effect",
        uniquePath: "/async-effect",
        path: "async-effect",
        file: "pulse/routes/async-effect.jsx",
      }
    ,
      {
        id: "/dynamic/:route_id/:optional_segment^/*",
        uniquePath: "/dynamic/:route_id/:optional_segment^/*",
        path: "dynamic/:route_id/:optional_segment?/*",
        file: "pulse/routes/dynamic/_route_id_f9a97bba/_optional_segment^_4de92ecc/__fb7ed505.jsx",
      }
    ],
  }
] satisfies RRRouteObject[];
