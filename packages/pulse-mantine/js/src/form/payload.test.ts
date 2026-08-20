import { describe, expect, it } from "bun:test";
import { stripFilesForSync } from "./payload";

describe("MantineForm payload helpers", () => {
	it("strips files from sync payloads", () => {
		const file = new File(["content"], "spec.pdf", {
			type: "application/pdf",
		});

		expect(
			stripFilesForSync({
				title: "Export queue",
				attachments: [file],
				nested: { docs: [file], keep: true },
			}),
		).toEqual({
			title: "Export queue",
			attachments: [],
			nested: { docs: [], keep: true },
		});
	});
});
