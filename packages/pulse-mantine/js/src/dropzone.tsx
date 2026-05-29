import {
	Dropzone as MantineDropzone,
	type DropzoneProps as MantineDropzoneProps,
	type FileWithPath,
} from "@mantine/dropzone";
import { useCallback } from "react";

import { useFormContext } from "./form/context";

export {
	DropzoneAccept,
	DropzoneFullScreen,
	DropzoneIdle,
	DropzoneReject,
	EXE_MIME_TYPE,
	IMAGE_MIME_TYPE,
	MIME_TYPES,
	MS_EXCEL_MIME_TYPE,
	MS_POWERPOINT_MIME_TYPE,
	MS_WORD_MIME_TYPE,
	PDF_MIME_TYPE,
} from "@mantine/dropzone";

export type { DropzoneProps, FileRejection, FileWithPath } from "@mantine/dropzone";

export interface PulseDropzoneProps extends MantineDropzoneProps {
	name?: string;
}

export function Dropzone({ name, onDrop, ...props }: PulseDropzoneProps) {
	const ctx = useFormContext();
	const handleDrop = useCallback(
		(files: FileWithPath[]) => {
			if (name && ctx) {
				ctx.form.setFieldValue(name, files);
				ctx.serverOnChange(name, false);
			}
			onDrop?.(files);
		},
		[ctx, name, onDrop],
	);

	return <MantineDropzone {...props} onDrop={handleDrop} />;
}
