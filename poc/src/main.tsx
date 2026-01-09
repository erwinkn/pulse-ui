import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import { App, getVdomForPath } from "./app";

createRoot(document.getElementById("root")!).render(
	<StrictMode>
		<App initialVdom={getVdomForPath("/")} initialRegistry={{}} />
	</StrictMode>,
);
