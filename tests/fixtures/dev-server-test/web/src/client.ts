import { initPulseClient } from "pulse-ui-client";

initPulseClient({
	wsUrl: `ws://${window.location.hostname}:8000/ws`,
});
