import type { HTMLAttributes } from "react";
import type { LinkItemType } from "../link-item";
import type * as Base from "./base";

type InternalComponents = Pick<
	typeof Base,
	| "SidebarFolder"
	| "SidebarFolderLink"
	| "SidebarFolderContent"
	| "SidebarFolderTrigger"
	| "SidebarItem"
>;

export function createLinkItemRenderer({
	SidebarFolder,
	SidebarFolderContent,
	SidebarFolderLink,
	SidebarFolderTrigger,
	SidebarItem,
}: InternalComponents) {
	/**
	 * Render sidebar items from page tree
	 */
	return function SidebarLinkItem({
		item,
		...props
	}: HTMLAttributes<HTMLElement> & {
		item: Exclude<LinkItemType, { type: "icon" }>;
	}) {
		if (item.type === "custom") return <div {...props}>{item.children}</div>;

		if (item.type === "menu")
			return (
				<SidebarFolder {...props}>
					{item.url ? (
						<SidebarFolderLink href={item.url} external={item.external}>
							{item.icon}
							{item.text}
						</SidebarFolderLink>
					) : (
						<SidebarFolderTrigger>
							{item.icon}
							{item.text}
						</SidebarFolderTrigger>
					)}
					<SidebarFolderContent>
						{item.items.map((child) => {
							const key =
								"url" in child && child.url
									? child.url
									: "text" in child && typeof child.text === "string"
										? child.text
										: child.type;

							return <SidebarLinkItem key={key} item={child} />;
						})}
					</SidebarFolderContent>
				</SidebarFolder>
			);

		return (
			<SidebarItem href={item.url} icon={item.icon} external={item.external} {...props}>
				{item.text}
			</SidebarItem>
		);
	};
}
