import { format } from "date-fns";

export function HomeWidget() {
	const today = format(new Date(), "PPPP");
	return (
		<div className="home-widget">
			<h2>Welcome Home</h2>
			<p>Today is {today}</p>
		</div>
	);
}
