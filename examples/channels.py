from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, override
from uuid import uuid4

import pulse as ps


@ps.react_component("ChannelTester", "~/components/channel-tester")
def ChannelTester(*, channelId: str, label: str): ...


@dataclass
class LogEntry:
	id: str
	message: str


def _timestamp() -> str:
	return datetime.now().strftime("%H:%M:%S")


def _format_payload(payload: Any) -> str:
	if payload is None:
		return "null"
	try:
		return json.dumps(payload, sort_keys=True)
	except (TypeError, ValueError):
		return repr(payload)


class ChannelInstanceState(ps.State):
	identifier: int
	label: str
	channel: ps.Channel
	client_events: list[LogEntry]
	server_events: list[LogEntry]
	client_pings: int
	client_requests: int
	notify_counter: int
	request_counter: int
	pending_request: bool
	last_client_response: str | None

	def __init__(self, identifier: int, label: str | None = None):
		self.identifier = identifier
		self.label = label or f"Channel #{identifier}"
		self.channel = ps.channel()
		self.client_events = []
		self.server_events = []
		self.client_pings = 0
		self.client_requests = 0
		self.notify_counter = 0
		self.request_counter = 0
		self.pending_request = False
		self.last_client_response = None
		self._cleanup_handlers: list[Callable[[], None]] = []
		self._register_handlers()

	def _register_handlers(self):
		self._cleanup_handlers.append(
			self.channel.on("client:ping", self._on_client_ping)
		)
		self._cleanup_handlers.append(
			self.channel.on("client:request", self._on_client_request)
		)

	def _push(self, attr: str, message: str) -> None:
		bucket: list[LogEntry] = getattr(self, attr)
		bucket.insert(0, LogEntry(uuid4().hex, message))
		if len(bucket) > 40:
			bucket.pop()

	def _push_client(self, message: str) -> None:
		self._push("client_events", message)

	def _push_server(self, message: str) -> None:
		self._push("server_events", message)

	def _on_client_ping(self, payload: Any) -> None:
		self.client_pings += 1
		self._push_client(
			f"{_timestamp()} · client ping #{self.client_pings}: {_format_payload(payload)}"
		)
		ack_payload = {
			"label": self.label,
			"ack": self.client_pings,
			"received": payload,
			"serverTime": _timestamp(),
		}
		self.channel.emit("server:notify", ack_payload)
		self._push_server(f"{_timestamp()} · sent ack for ping #{self.client_pings}")

	async def _on_client_request(self, payload: Any) -> Any:
		self.client_requests += 1
		self._push_client(
			f"{_timestamp()} · client request #{self.client_requests}: {_format_payload(payload)}"
		)
		response = {
			"label": self.label,
			"sequence": self.client_requests,
			"received": payload,
			"serverTime": _timestamp(),
		}
		self._push_server(
			f"{_timestamp()} · responded to client request #{self.client_requests}"
		)
		return response

	def send_notification(self) -> None:
		self.notify_counter += 1
		payload = {
			"label": self.label,
			"sequence": self.notify_counter,
			"serverTime": _timestamp(),
			"type": "notify",
		}
		self._push_server(
			f"{_timestamp()} · server notify #{self.notify_counter}: {_format_payload(payload)}"
		)
		self.channel.emit("server:notify", payload)

	async def request_client(self) -> None:
		sequence = self.request_counter + 1
		self.request_counter = sequence
		payload = {
			"label": self.label,
			"sequence": sequence,
			"serverTime": _timestamp(),
			"type": "request",
		}
		self.pending_request = True
		self._push_server(
			f"{_timestamp()} · server request #{sequence}: {_format_payload(payload)}"
		)
		try:
			response = await self.channel.request(
				"server:ask",
				payload,
				timeout=5.0,
			)
		except ps.ChannelTimeout:
			self._push_server(f"{_timestamp()} · server request #{sequence}: timed out")
		else:
			response_str = _format_payload(response)
			self.last_client_response = response_str
			self._push_server(
				f"{_timestamp()} · server request #{sequence}: response {response_str}"
			)
		finally:
			self.pending_request = False

	@override
	def on_dispose(self) -> None:
		for cleanup in self._cleanup_handlers:
			try:
				cleanup()
			except Exception:
				pass
		self._cleanup_handlers.clear()


@ps.component
def ChannelInstance(
	instance_id: int,
	*,
	label: str | None = None,
	show_remove: bool = True,
	on_remove: ps.EventHandler0 | None = None,
	key: str | None = None,
):
	state = ps.states(ChannelInstanceState(instance_id, label))
	channel = state.channel

	header_actions = [
		ps.span(
			f"Pings: {state.client_pings} · Requests: {state.client_requests}",
			className="text-xs text-slate-400",
		),
		ps.span(
			f"Server notify: {state.notify_counter} · Server ask: {state.request_counter}",
			className="text-xs text-slate-400",
		),
	]
	if show_remove and on_remove is not None:
		header_actions.append(
			ps.button(
				"Remove",
				onClick=on_remove,
				className="btn-light btn-xs",
			)
		)

	server_buttons = [
		ps.button(
			"Send server notify",
			onClick=state.send_notification,
			className="btn-secondary btn-sm",
		),
		ps.button(
			"Ask client",
			onClick=state.request_client,
			className="btn-primary btn-sm",
			disabled=state.pending_request,
		),
	]

	pending_note: list[ps.Element] = []
	if state.pending_request:
		pending_note.append(
			ps.p(
				"Waiting for client response…",
				className="text-xs text-amber-300",
			)
		)

	if state.last_client_response:
		pending_note.append(
			ps.p(
				f"Last client response: {state.last_client_response}",
				className="text-xs font-mono text-emerald-300 break-words",
			)
		)

	client_log_body: ps.Element
	if not state.client_events:
		client_log_body = ps.p(
			"No client events yet.",
			className="text-xs text-slate-500",
		)
	else:
		client_log_body = ps.ul(className="space-y-2")[
			ps.For(
				state.client_events,
				lambda entry, idx: ps.li(
					entry.message,
					key=entry.id,
					className="text-xs font-mono text-slate-200 break-words",
				),
			)
		]

	server_log_body: ps.Element
	if not state.server_events:
		server_log_body = ps.p(
			"No server events yet.",
			className="text-xs text-slate-500",
		)
	else:
		server_log_body = ps.ul(className="space-y-2")[
			ps.For(
				state.server_events,
				lambda entry, idx: ps.li(
					entry.message,
					key=entry.id,
					className="text-xs font-mono text-slate-200 break-words",
				),
			)
		]

	return ps.div(
		className="rounded-lg border border-slate-800 bg-slate-900 p-4 space-y-4 shadow",
		key=key,
	)[
		ps.div(className="flex items-start justify-between gap-4")[
			ps.div(className="space-y-1")[
				ps.p(
					"Channel instance",
					className="text-xs uppercase tracking-wide text-slate-400",
				),
				ps.h3(
					state.label,
					className="text-lg font-semibold text-slate-100",
				),
				ps.p(
					f"Channel ID: {channel.id}",
					className="font-mono text-xs text-slate-500 break-all",
				),
			],
			ps.div(className="flex flex-col items-end gap-2")[*header_actions],
		],
		ps.div(className="flex flex-wrap gap-2")[*server_buttons],
		*pending_note,
		ChannelTester(channelId=channel.id, label=state.label),
		ps.div(className="grid gap-3 md:grid-cols-2")[
			ps.div(className="space-y-2")[
				ps.h4(
					"Client → Server",
					className="text-sm font-semibold text-slate-100",
				),
				ps.div(
					className="max-h-48 overflow-auto rounded border border-slate-800 bg-slate-950 p-3"
				)[client_log_body,],
			],
			ps.div(className="space-y-2")[
				ps.h4(
					"Server → Client",
					className="text-sm font-semibold text-slate-100",
				),
				ps.div(
					className="max-h-48 overflow-auto rounded border border-slate-800 bg-slate-950 p-3"
				)[server_log_body,],
			],
		],
	]


class ChannelsDemoState(ps.State):
	instances: list[int]
	next_id: int
	visible: bool

	def __init__(self):
		self.instances = [1, 2]
		self.next_id = 3
		self.visible = True

	def add_instance(self):
		identifier = self.next_id
		self.next_id += 1
		self.instances = [*self.instances, identifier]

	def remove_last(self):
		if not self.instances:
			return
		self.instances = self.instances[:-1]

	def remove_instance(self, identifier: int):
		self.instances = [item for item in self.instances if item != identifier]

	def clear(self):
		self.instances = []

	def toggle_visible(self):
		self.visible = not self.visible

	def reverse_order(self):
		self.instances = list(reversed(self.instances))

	def rotate_order(self):
		if len(self.instances) <= 1:
			return
		first, *rest = self.instances
		self.instances = [*rest, first]

	def shuffle_order(self):
		if len(self.instances) <= 1:
			return
		shuffled = list(self.instances)
		random.shuffle(shuffled)
		self.instances = shuffled


@ps.component
def ChannelPlayground():
	state = ps.states(ChannelsDemoState)

	def render_instance(identifier: int, idx: int):
		return ChannelInstance(
			identifier,
			label=f"Tester {identifier}",
			on_remove=lambda value=identifier: state.remove_instance(value),
			key=f"instance-{identifier}",
		)

	if state.visible:
		if state.instances:
			body: ps.Element = ps.div(className="grid gap-4 md:grid-cols-2")[
				ps.For(state.instances, render_instance)
			]
		else:
			body = ps.p(
				"No channel testers mounted. Use the controls above to add one.",
				className="text-sm text-slate-400",
			)
	else:
		body = ps.p(
			"Channel testers are hidden. Toggle visibility to mount them.",
			className="text-sm text-slate-400",
		)

	return ps.div(className="space-y-8")[
		ps.div(className="space-y-3")[
			ps.h2(
				"Channel playground",
				className="text-2xl font-semibold text-slate-100",
			),
			ps.p(
				"Mount, unmount, and reorder channel-backed components. Use the client and server controls to exercise channel events and request/response flows.",
				className="text-sm text-slate-400",
			),
			ps.div(className="flex flex-wrap gap-2")[
				ps.button(
					"Add tester",
					onClick=state.add_instance,
					className="btn-primary btn-sm",
				),
				ps.button(
					"Remove last",
					onClick=state.remove_last,
					className="btn-light btn-sm",
					disabled=not state.instances,
				),
				ps.button(
					"Clear all",
					onClick=state.clear,
					className="btn-light btn-sm",
					disabled=not state.instances,
				),
				ps.button(
					"Toggle visibility",
					onClick=state.toggle_visible,
					className="btn-secondary btn-sm",
				),
				ps.button(
					"Reverse order",
					onClick=state.reverse_order,
					className="btn-secondary btn-sm",
					disabled=len(state.instances) <= 1,
				),
				ps.button(
					"Rotate order",
					onClick=state.rotate_order,
					className="btn-secondary btn-sm",
					disabled=len(state.instances) <= 1,
				),
				ps.button(
					"Shuffle order",
					onClick=state.shuffle_order,
					className="btn-secondary btn-sm",
					disabled=len(state.instances) <= 1,
				),
			],
		],
		body,
	]


@ps.component
def SecondaryRoute():
	return ps.div(className="space-y-6")[
		ps.h2(
			"Secondary route",
			className="text-2xl font-semibold text-slate-100",
		),
		ps.p(
			"Navigate back and forth to confirm channel cleanup on route unmount. This route mounts a single channel instance.",
			className="text-sm text-slate-400",
		),
		ChannelInstance(
			1000,
			label="Secondary route tester",
			show_remove=False,
			key="secondary-instance",
		),
	]


@ps.component
def ChannelsLayout():
	return ps.div(className="min-h-screen bg-slate-950 text-slate-100")[
		ps.header(className="border-b border-slate-800 bg-slate-900")[
			ps.div(
				className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4"
			)[
				ps.h1("Pulse channel tester", className="text-xl font-semibold"),
				ps.nav(className="flex gap-3 text-sm text-slate-300")[
					ps.Link("Playground", to="/", className="hover:text-white"),
					ps.Link(
						"Secondary route", to="/secondary", className="hover:text-white"
					),
				],
			]
		],
		ps.main(className="py-10")[
			ps.div(className="mx-auto max-w-5xl space-y-8 px-6")[ps.Outlet()]
		],
	]


app = ps.App(
	routes=[
		ps.Layout(
			ChannelsLayout,
			children=[
				ps.Route("/", ChannelPlayground),
				ps.Route("/secondary", SecondaryRoute),
			],
		)
	]
)
