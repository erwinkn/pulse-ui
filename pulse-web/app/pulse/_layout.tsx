import { PulseProvider, type PulseConfig } from "pulse-react/pulse";
import { Outlet } from "react-router";

// This config is imported by the layout and used to initialize the client
export const config: PulseConfig = {
  serverAddress: "http://localhost:8000",
};

export default function PulseLayout() {
  return (
    <PulseProvider config={config}>
      <Outlet />
    </PulseProvider>
  );
}
