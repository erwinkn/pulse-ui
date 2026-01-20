import type { CSSProperties } from "react";
import { DocsLayout } from "@/components/layout/docs";
import { baseOptions } from "@/lib/layout.shared";
import { source } from "@/lib/source";

export default function Layout({ children }: LayoutProps<"/docs/[[...slug]]">) {
	return (
		<DocsLayout
			tree={source.getPageTree()}
			{...baseOptions()}
			sidebar={{
				tabs: {
					transform(option, node) {
						if (!node.icon) return option;
						const color = "var(--color-pulse-marine)";
						return {
							...option,
							icon: (
								<div
									className="flex items-center justify-center rounded-lg size-full text-(--tab-color) [&_svg]:size-4.5 max-md:bg-(--tab-color)/10 max-md:border max-md:p-1.5"
									style={
										{
											"--tab-color": color,
										} as CSSProperties
									}
								>
									{node.icon}
								</div>
							),
						};
					},
				},
			}}
		>
			{children}
		</DocsLayout>
	);
}
