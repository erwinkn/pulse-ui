import {
	PulseForm as PulseForm_5,
	PulseView as PulseView_7,
	useLocation,
	useNavigate,
	useParams,
} from "pulse-ui-client";
import { Link as Link_1, Outlet as Outlet_3 } from "react-router";

// Unified Registry
const __registry = {
	1: Link_1,
	3: Outlet_3,
	5: PulseForm_5,
	7: PulseView_7,
};

const path = "/";

export default function RouteComponent() {
	const location = useLocation();
	const params = useParams();
	const navigate = useNavigate();

	return (
		<PulseView_7
			key={path}
			registry={__registry}
			path={path}
			location={location}
			params={params}
			navigate={navigate}
		/>
	);
}
