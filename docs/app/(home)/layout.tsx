import { HomeLayout } from "fumadocs-ui/layouts/home";
import { baseOptions } from "@/lib/layout.shared";

export default function Layout({ children }: LayoutProps<"/">) {
	return (
		<HomeLayout {...baseOptions()} className="[--fd-layout-width:72rem]">
			{children}
		</HomeLayout>
	);
}
