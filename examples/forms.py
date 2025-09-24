"""Example application demonstrating Pulse form helpers."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

import pulse as ps
from fastapi import UploadFile



def summarize_form_value(value: Any) -> Any:
    if isinstance(value, UploadFile):
        return {
            "filename": value.filename,
            "content_type": value.content_type,
            "size": value.size,
        }
    return value


def summarize_form_payload(data: ps.FormData) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, list):
            summary[key] = [summarize_form_value(item) for item in value]
        else:
            summary[key] = summarize_form_value(value)
    return summary

class FormLogState(ps.State):
    auto_submissions: list[dict[str, Any]] = []
    manual_submissions: list[dict[str, Any]] = []
    last_submission_sid: str | None = None

    async def handle_auto(self, data: ps.FormData) -> None:
        await asyncio.sleep(1)
        summary = summarize_form_payload(data)
        self.auto_submissions.append(
            {
                "received_at": datetime.utcnow().isoformat(),
                "fields": summary,
            }
        )
        self.last_submission_sid = ps.session_id()

    async def handle_manual(self, data: ps.FormData) -> None:
        await asyncio.sleep(1)
        summary = summarize_form_payload(data)
        self.manual_submissions.append(
            {
                "received_at": datetime.utcnow().isoformat(),
                "fields": summary,
            }
        )
        self.last_submission_sid = ps.session_id()


def render_submission_list(title: str, entries: list[dict[str, Any]]):
    if not entries:
        body = ps.p("No submissions yet.", className="text-sm text-gray-600")
    else:
        body = ps.ul(
            *[
                ps.li(
                    ps.pre(
                        json.dumps(entry, indent=2, default=str),
                        className="bg-gray-100 rounded p-2 overflow-x-auto text-xs",
                    ),
                    key=f"entry-{idx}",
                    className="mb-2",
                )
                for idx, entry in enumerate(reversed(entries))
            ],
            className="list-disc pl-4",
        )
    return ps.section(
        ps.h3(title, className="text-lg font-semibold mb-2"),
        body,
        className="space-y-2",
    )


@ps.component
def FormsPage():
    state = ps.states(FormLogState)

    manual_form = ps.setup(lambda: ps.ManualForm(state.handle_manual))
    manual_props = manual_form.props()

    return ps.div(
        ps.h1("Pulse Forms Demo", className="text-2xl font-bold mb-4"),
        ps.p(
            "This page shows the built-in ps.Form helper and manual Form usage, "
            "including handling text fields and file uploads.",
            className="text-sm text-gray-600 mb-6",
        ),
        ps.section(
            ps.h2("Security context", className="text-xl font-semibold mb-3"),
            ps.p(f"Current session ID: {ps.session_id()}", className="text-sm"),
            ps.p(
                "Last submission session ID: "
                + (state.last_submission_sid or "<none>"),
                className="text-sm",
            ),
            className="mb-8 space-y-2",
        ),
        ps.section(
            ps.h2("Auto-managed form", className="text-xl font-semibold mb-3"),
            ps.Form(key="auto-demo", onSubmit=state.handle_auto)[
                ps.label(
                    "Full name", htmlFor="auto-name", className="block text-sm mb-1"
                ),
                ps.input(
                    id="auto-name",
                    name="name",
                    type="text",
                    placeholder="Ada Lovelace",
                    required=True,
                    className="border rounded px-2 py-1 w-full mb-2",
                ),
                ps.label("Bio", htmlFor="auto-bio", className="block text-sm mb-1"),
                ps.textarea(
                    id="auto-bio",
                    name="bio",
                    rows=3,
                    className="border rounded px-2 py-1 w-full mb-2",
                ),
                ps.label(
                    "Profile picture",
                    htmlFor="auto-avatar",
                    className="block text-sm mb-1",
                ),
                ps.input(
                    id="auto-avatar",
                    name="avatar",
                    type="file",
                    accept="image/*",
                    className="mb-2",
                ),
                ps.label(
                    "Attachments",
                    htmlFor="auto-files",
                    className="block text-sm mb-1",
                ),
                ps.input(
                    id="auto-files",
                    name="attachments",
                    type="file",
                    multiple=True,
                    className="mb-3",
                ),
                ps.button(
                    "Submit",
                    type="submit",
                    className="bg-blue-600 text-white rounded px-3 py-1",
                ),
            ],
            className="mb-8 space-y-3",
        ),
        render_submission_list("Auto form submissions", state.auto_submissions),
        ps.section(className="mb-8 space-y-3")[
            ps.h2("Manually managed form", className="text-xl font-semibold mb-3"),
            ps.h3(f"Is submitting: {manual_form.is_submitting}"),
            ps.form(**manual_props)[
                ps.label(
                    "Project", htmlFor="manual-project", className="block text-sm mb-1"
                ),
                ps.input(
                    id="manual-project",
                    name="project",
                    type="text",
                    placeholder="Pulse",
                    required=True,
                    className="border rounded px-2 py-1 w-full mb-2",
                ),
                ps.label(
                    "Notes", htmlFor="manual-notes", className="block text-sm mb-1"
                ),
                ps.textarea(
                    id="manual-notes",
                    name="notes",
                    rows=3,
                    className="border rounded px-2 py-1 w-full mb-2",
                ),
                ps.label(
                    "Specification",
                    htmlFor="manual-spec",
                    className="block text-sm mb-1",
                ),
                ps.input(
                    id="manual-spec",
                    name="spec",
                    type="file",
                    className="mb-3",
                ),
                ps.button(
                    "Submit manually",
                    type="submit",
                    className="bg-green-600 text-white rounded px-3 py-1",
                ),
            ],
        ],
        render_submission_list("Manual form submissions", state.manual_submissions),
        className="space-y-10 max-w-3xl mx-auto py-10",
    )


app = ps.App(
    routes=[
        ps.Route("/", FormsPage),
    ]
)
