import Link from "next/link";

export default function HomePage() {
	return (
		<div className="flex flex-1 flex-col items-center justify-center gap-6 px-6 text-center">
			<div className="space-y-3">
				<h1 className="text-4xl font-semibold tracking-tight">Pulse</h1>
				<p className="text-fd-muted-foreground">
					Full-stack Python framework for reactive web apps.
				</p>
			</div>
			<div className="flex flex-wrap items-center justify-center gap-3">
				<Link
					href="/docs/getting-started/install"
					className="inline-flex items-center rounded-md bg-fd-primary px-4 py-2 text-sm font-medium text-fd-primary-foreground"
				>
					Get started
				</Link>
				<Link
					href="/docs"
					className="inline-flex items-center rounded-md border px-4 py-2 text-sm font-medium"
				>
					Docs
				</Link>
			</div>
		</div>
	);
}
