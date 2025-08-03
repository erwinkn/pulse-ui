import { PulseProvider, type PulseConfig } from "~/pulse-lib/pulse";
import { Outlet } from "react-router";

// This config is imported by the layout and used to initialize the client
export const config: PulseConfig = {
  serverAddress: "127.0.0.1",
  serverPort: 8000,
};

export default function PulseLayout() {
  return (
    <PulseProvider config={config}>
      <Outlet />
    </PulseProvider>
  );
}
