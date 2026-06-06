import { describe, expect, it } from "bun:test";
import { extractDataAndFiles, stripFilesForSync } from "./payload";

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

	it("extracts files for multipart submit data", () => {
		const file = new File(["content"], "spec.pdf", {
			type: "application/pdf",
		});

		const { dataWithoutFiles, filesByPath } = extractDataAndFiles({
			title: "Export queue",
			attachments: [file],
		});

		expect(dataWithoutFiles).toEqual({
			title: "Export queue",
			attachments: [undefined],
		});
		expect(filesByPath.get("attachments.0")).toEqual([file]);
	});
});
