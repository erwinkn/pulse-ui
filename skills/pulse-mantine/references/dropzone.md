# Dropzone

`@mantine/dropzone` wrapper: drag-and-drop file uploads. Available since pulse-mantine 0.1.34.

```python
from pulse_mantine import (
    Dropzone, DropzoneAccept, DropzoneReject, DropzoneIdle, DropzoneFullScreen,
    MIME_TYPES, IMAGE_MIME_TYPE, PDF_MIME_TYPE,
    MS_WORD_MIME_TYPE, MS_EXCEL_MIME_TYPE, MS_POWERPOINT_MIME_TYPE,
)
```

The `@mantine/dropzone` npm package (`^8.0.0`) is registered automatically via `ps.require` when `pulse_mantine` is imported, and its stylesheet is auto-imported after `@mantine/core` styles — no manual setup.

## Basic Usage

```python
Dropzone(
    onDrop=handle_drop,
    onReject=handle_reject,
    accept=IMAGE_MIME_TYPE,
    maxSize=5 * 1024**2,
)[
    Group(justify="center", gap="xl", mih=180, style={"pointerEvents": "none"})[
        DropzoneAccept()[Text("Drop it")],
        DropzoneReject()[Text("Not accepted")],
        DropzoneIdle()[Text("Drag files here or click to select")],
    ],
]
```

`DropzoneAccept` / `DropzoneReject` / `DropzoneIdle` render their children only in the matching drag state.

## Accepted Files

```python
accept=["image/png", "application/pdf"]        # list of mime types
accept={"image/*": [".png", ".jpg", ".jpeg"]}  # mime type -> allowed extensions
accept=IMAGE_MIME_TYPE                         # predefined groups (see imports above)
accept=[MIME_TYPES["csv"], MIME_TYPES["xlsx"]] # by extension name
```

Limits: `maxFiles` (count), `maxSize` / `minSize` (bytes per file), `multiple=False` (single file). Behavior: `disabled`, `loading` (overlay), `activateOnClick` / `activateOnDrag` / `activateOnKeyboard`.

## Callbacks

- `onDrop(files)` — fires with the accepted files after a drop or file-picker selection.
- `onReject(rejections)` — fires with rejected files; each rejection is `{"file": ..., "errors": [{"code": ..., "message": ...}]}`.
- Also: `onDragEnter`, `onDragLeave`, `onDragOver`, `onFileDialogOpen`, `onFileDialogCancel`, `onError`.

**The server never receives file contents through these callbacks.** Callback args cross the wire through the Pulse serializer, which only sends JSON-compatible data — a browser `File` arrives as a small metadata dict (its `path`/`relativePath`; `name`/`size`/`type` live on the `File` prototype and don't survive serialization). Use `onDrop`/`onReject` for UX (counts, error messages), not for reading files.

## Receiving Files: Use a Form

Give the Dropzone a `name=` and render it inside a `MantineForm`. Dropped files are written into form state and arrive as `ps.UploadFile` on submit:

```python
form = MantineForm(initialValues={"notes": "", "attachments": []})

async def handle_submit(values):
    for file in values["attachments"]:  # list[ps.UploadFile]
        data = await file.read()

return form.render(onSubmit=handle_submit)[
    Textarea(name="notes"),
    Dropzone(name="attachments", accept=PDF_MIME_TYPE)[
        DropzoneIdle()[Text("Drop PDFs here")],
    ],
    Button("Upload", type="submit"),
]
```

Each drop replaces the field value with the newly dropped files (it is a `set_field_value`, not an append). Files are stripped from value-sync payloads, so a synced form (`syncMode="change"`) is safe — `form.values` shows the field as `[]`; the files arrive only on submit. See File Uploads in `references/forms.md`.

## Fullscreen Variant

```python
DropzoneFullScreen(active=True, accept=IMAGE_MIME_TYPE)[
    Text("Drop files anywhere on the page"),
]
```

`DropzoneFullScreen` is the plain Mantine component — it has no `name=` form integration, so use it for UX only; receive files through a regular `Dropzone(name=...)` in a form.
