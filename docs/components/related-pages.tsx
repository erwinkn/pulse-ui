"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { type ReactNode, useMemo } from "react";
import { source } from "@/lib/source";

interface RelatedPagesProps {
	/** Maximum number of related pages to show */
	max?: number;
}

export function RelatedPages({ max = 3 }: RelatedPagesProps) {
	const pathname = usePathname();

	const relatedPages = useMemo(() => {
		const tree = source.getPageTree();
		const currentPath = pathname.replace(/^\/docs/, "");

		// Find the current section (parent folder)
		const pathParts = currentPath.split("/").filter(Boolean);
		if (pathParts.length === 0) return [];

		// Get all pages from the tree, using Map to deduplicate by URL
		const pageMap = new Map<string, { url: string; name: ReactNode; description?: ReactNode }>();

		function collectPages(node: typeof tree | (typeof tree.children)[number], depth = 0) {
			if ("children" in node) {
				for (const child of node.children) {
					collectPages(child, depth + 1);
				}
			}
			if ("url" in node && node.type === "page" && !node.external && !pageMap.has(node.url)) {
				pageMap.set(node.url, {
					url: node.url,
					name: node.name,
					description: node.description,
				});
			}
		}

		collectPages(tree);
		const allPages = Array.from(pageMap.values());

		// Find pages in the same section (share the same parent path)
		const currentSection = pathParts.slice(0, -1).join("/");
		const sameSection = allPages.filter((page) => {
			const pagePathParts = page.url
				.replace(/^\/docs/, "")
				.split("/")
				.filter(Boolean);
			const pageSection = pagePathParts.slice(0, -1).join("/");
			return pageSection === currentSection && page.url !== pathname;
		});

		// If we have pages in the same section, prioritize those
		if (sameSection.length > 0) {
			return sameSection.slice(0, max);
		}

		// Otherwise, find pages in sibling or parent sections
		const siblingPages = allPages.filter((page) => {
			return page.url !== pathname && page.url.startsWith("/docs");
		});

		// Shuffle and return a subset
		return siblingPages.sort(() => Math.random() - 0.5).slice(0, max);
	}, [pathname, max]);

	if (relatedPages.length === 0) return null;

	return (
		<div className="mt-8 border-t pt-8">
			<h3 className="text-sm font-medium text-fd-muted-foreground mb-4">What to read next</h3>
			<div className="grid gap-3">
				{relatedPages.map((page) => (
					<Link
						key={page.url}
						href={page.url}
						className="group flex items-center gap-3 rounded-lg border p-3 text-sm transition-colors hover:bg-fd-accent/50"
					>
						<div className="flex-1 min-w-0">
							<p className="font-medium truncate group-hover:text-fd-primary transition-colors">
								{page.name}
							</p>
							{page.description && (
								<p className="text-fd-muted-foreground truncate text-xs mt-0.5">
									{page.description}
								</p>
							)}
						</div>
						<ArrowRight className="size-4 shrink-0 text-fd-muted-foreground group-hover:text-fd-primary transition-colors" />
					</Link>
				))}
			</div>
		</div>
	);
}
