import { initPulseClient } from "pulse-ui-client";
import "~/app.css";

initPulseClient({
	wsUrl: `ws://${window.location.hostname}:8000/ws`,
});
