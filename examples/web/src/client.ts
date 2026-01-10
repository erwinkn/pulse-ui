import { initPulseClient } from "pulse-ui-client";
import "~/app.css";

initPulseClient({
	wsUrl: `http://${window.location.hostname}:8000`,
});
