import { source } from "@/lib/source";

export const revalidate = false;

/**
 * llms.txt index - returns a list of all doc pages with links to their MDX content.
 * LLMs can use this to discover available documentation and fetch individual pages.
 */
export function GET() {
	const pages = source.getPages();

	const lines = [
		"# Pulse",
		"",
		"> Full-stack Python framework for interactive web apps. React frontend with WebSocket-driven UI updates.",
		"",
		"## Docs",
		"",
		...pages.map((page) => `- [${page.data.title}](${page.url}.mdx)`),
		"",
		"## Full docs",
		"",
		"For full documentation content, fetch /llms-full.txt",
	];

	return new Response(lines.join("\n"), {
		headers: {
			"Content-Type": "text/plain",
		},
	});
}
