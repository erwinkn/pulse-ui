import type { Location, NavigateFn, Params } from "pulse-ui-client";
import { PulseRouterProvider } from "pulse-ui-client";

export interface LayoutProps {
	location: Location;
	params: Params;
	navigate: NavigateFn;
	children: React.ReactNode;
}

export default function PulseLayout({ location, params, navigate, children }: LayoutProps) {
	return (
		<PulseRouterProvider location={location} params={params} navigate={navigate}>
			{children}
		</PulseRouterProvider>
	);
}
