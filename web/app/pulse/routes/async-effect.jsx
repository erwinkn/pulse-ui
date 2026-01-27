import { Link as Link_1, Outlet as Outlet_3 } from "react-router";
import { PulseForm as PulseForm_5, PulseView as PulseView_12 } from "pulse-ui-client";
import { lazy as lazy_8 } from "react";

// Lazy imports
const __components_date_picker_7 = () => import("~/components/date-picker");

// Constants
const _const_9 = lazy_8(__components_date_picker_7);

// Unified Registry
const __registry = {
  "1": Link_1,
  "3": Outlet_3,
  "5": PulseForm_5,
  "7": __components_date_picker_7,
  "8": lazy_8,
  "12": PulseView_12,
  "9": _const_9,
};

const path = "/async-effect";

export default function RouteComponent() {
  return (
    <PulseView_12 key={path} registry={__registry} path={path} />
  );
}

// Action and loader headers are not returned automatically
function hasAnyHeaders(headers) {
  return [...headers].length > 0;
}

export function headers({ actionHeaders, loaderHeaders }) {
  return hasAnyHeaders(actionHeaders) ? actionHeaders : loaderHeaders;
}