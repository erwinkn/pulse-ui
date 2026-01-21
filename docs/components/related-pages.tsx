"use client";

import type { Node } from "fumadocs-core/page-tree";
import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { type ReactNode, useMemo } from "react";
import { source } from "@/lib/source";

interface RelatedPagesProps {
	/** Maximum number of related pages to show */
	max?: number;
}

// Get parent section from a docs URL (e.g., "/docs/guides/intro" -> "guides")
function getSection(url: string) {
	const parts = url
		.replace(/^\/docs/, "")
		.split("/")
		.filter(Boolean);
	return parts.slice(0, -1).join("/");
}

export function RelatedPages({ max = 3 }: RelatedPagesProps) {
	const pathname = usePathname();

	const relatedPages = useMemo(() => {
		const tree = source.getPageTree();
		const currentSection = getSection(pathname);

		// Collect all internal pages except current
		const pages: { url: string; name: ReactNode; description?: ReactNode }[] = [];

		function collectPages(node: Node) {
			if (node.type === "page") {
				if (!node.external && node.url !== pathname) {
					pages.push({ url: node.url, name: node.name, description: node.description });
				}
			} else if (node.type === "folder") {
				for (const child of node.children) {
					collectPages(child);
				}
			}
		}

		for (const child of tree.children) {
			collectPages(child);
		}

		// Sort alphabetically by URL
		pages.sort((a, b) => a.url.localeCompare(b.url));

		// Prefer pages in the same section
		const sameSection = pages.filter((p) => getSection(p.url) === currentSection);
		if (sameSection.length > 0) {
			return sameSection.slice(0, max);
		}

		return pages.slice(0, max);
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
