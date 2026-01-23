import { notFound } from "next/navigation";
import { LogoPlayground } from "./logo-playground.client";

export default function LogoPlaygroundPage() {
	if (process.env.NODE_ENV === "production") {
		notFound();
	}

	return <LogoPlayground />;
}
