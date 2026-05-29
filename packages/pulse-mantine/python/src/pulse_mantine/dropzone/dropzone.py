from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal, TypedDict, Unpack

import pulse as ps

from pulse_mantine.core.box import BoxProps
from pulse_mantine.core.styles import StyleFn

DropzoneStatus = Literal["idle", "accept", "reject"]
DropzoneStylesNames = Literal["root", "inner"]
DropzoneAttributes = dict[DropzoneStylesNames, dict[str, Any]]
DropzoneStyles = dict[DropzoneStylesNames, ps.CSSProperties]
DropzoneClassNames = dict[DropzoneStylesNames, str]
DropzoneAcceptSpec = dict[str, Sequence[str]] | Sequence[str]
DropzoneFile = Any


class DropzoneError(TypedDict):
	code: str
	message: str


class FileRejection(TypedDict):
	file: DropzoneFile
	errors: Sequence[DropzoneError]


class DropzoneCtx(TypedDict):
	accept: bool
	reject: bool
	idle: bool


class DropzoneProps(BoxProps, total=False):
	name: str
	"""Field name used when Dropzone is rendered inside MantineForm."""
	accept: DropzoneAcceptSpec
	"""Accepted mime types or a mapping from mime type to allowed extensions."""
	activateOnClick: bool
	"""Determines whether clicking the dropzone opens the file picker @default `true`."""
	activateOnDrag: bool
	"""Determines whether dragging files over the dropzone activates it @default `true`."""
	activateOnKeyboard: bool
	"""Determines whether keyboard interaction opens the file picker @default `true`."""
	autoFocus: bool
	"""Determines whether the dropzone should be focused on mount."""
	disabled: bool
	"""Disables drag, drop, and click interactions."""
	fullScreen: bool
	"""Determines whether the dropzone covers the viewport."""
	loading: bool
	"""Shows loading overlay and disables user interaction."""
	maxFiles: int
	"""Maximum number of files that can be accepted."""
	maxSize: int
	"""Maximum individual file size in bytes."""
	minSize: int
	"""Minimum individual file size in bytes."""
	multiple: bool
	"""Determines whether multiple files can be selected @default `true`."""
	onDrop: ps.EventHandler1[list[DropzoneFile]]
	"""Called with accepted files when files are dropped or selected."""
	onReject: ps.EventHandler1[list[FileRejection]]
	"""Called with rejected files when validation fails."""
	onDragEnter: ps.EventHandler0
	onDragLeave: ps.EventHandler0
	onDragOver: ps.EventHandler0
	onFileDialogCancel: ps.EventHandler0
	onFileDialogOpen: ps.EventHandler0
	onError: ps.EventHandler1[Any]
	openRef: Any
	"""React ref used to open the file picker manually."""
	preventDropOnDocument: bool
	"""Prevents files from being dropped on the document outside the dropzone."""
	useFsAccessApi: bool
	"""Uses the File System Access API to open the picker when available."""

	# Styles API props
	unstyled: bool
	"""Removes default styles from the component."""
	variant: str
	"""Component variant, if applicable."""
	classNames: (
		DropzoneClassNames | StyleFn[DropzoneProps, DropzoneCtx, DropzoneClassNames]
	)
	"""Additional class names passed to elements."""
	styles: DropzoneStyles | StyleFn[DropzoneProps, DropzoneCtx, DropzoneStyles]
	"""Additional styles passed to elements."""
	attributes: DropzoneAttributes
	"""Additional attributes passed to elements."""


class DropzoneFullScreenProps(DropzoneProps, total=False):
	active: bool
	"""Determines whether full screen dropzone is active."""


class DropzoneStatusProps(BoxProps, total=False):
	children: ps.Node | Sequence[ps.Node]


MIME_TYPES = {
	"png": "image/png",
	"gif": "image/gif",
	"jpeg": "image/jpeg",
	"svg": "image/svg+xml",
	"webp": "image/webp",
	"avif": "image/avif",
	"heic": "image/heic",
	"heif": "image/heif",
	"mp4": "video/mp4",
	"zip": "application/zip",
	"rar": "application/x-rar",
	"7z": "application/x-7z-compressed",
	"csv": "text/csv",
	"pdf": "application/pdf",
	"doc": "application/msword",
	"docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
	"xls": "application/vnd.ms-excel",
	"xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
	"ppt": "application/vnd.ms-powerpoint",
	"pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
	"exe": "application/vnd.microsoft.portable-executable",
}
IMAGE_MIME_TYPE = [
	MIME_TYPES["png"],
	MIME_TYPES["gif"],
	MIME_TYPES["jpeg"],
	MIME_TYPES["svg"],
	MIME_TYPES["webp"],
	MIME_TYPES["avif"],
	MIME_TYPES["heic"],
	MIME_TYPES["heif"],
]
PDF_MIME_TYPE = [MIME_TYPES["pdf"]]
MS_WORD_MIME_TYPE = [MIME_TYPES["doc"], MIME_TYPES["docx"]]
MS_EXCEL_MIME_TYPE = [MIME_TYPES["xls"], MIME_TYPES["xlsx"]]
MS_POWERPOINT_MIME_TYPE = [MIME_TYPES["ppt"], MIME_TYPES["pptx"]]
EXE_MIME_TYPE = [MIME_TYPES["exe"]]


@ps.react_component(ps.Import("Dropzone", "pulse-mantine"))
def Dropzone(
	*children: ps.Node, key: str | None = None, **props: Unpack[DropzoneProps]
): ...


@ps.react_component(ps.Import("DropzoneAccept", "pulse-mantine"))
def DropzoneAccept(
	*children: ps.Node, key: str | None = None, **props: Unpack[DropzoneStatusProps]
): ...


@ps.react_component(ps.Import("DropzoneReject", "pulse-mantine"))
def DropzoneReject(
	*children: ps.Node, key: str | None = None, **props: Unpack[DropzoneStatusProps]
): ...


@ps.react_component(ps.Import("DropzoneIdle", "pulse-mantine"))
def DropzoneIdle(
	*children: ps.Node, key: str | None = None, **props: Unpack[DropzoneStatusProps]
): ...


@ps.react_component(ps.Import("DropzoneFullScreen", "pulse-mantine"))
def DropzoneFullScreen(
	*children: ps.Node,
	key: str | None = None,
	**props: Unpack[DropzoneFullScreenProps],
): ...
