from __future__ import annotations

import json
from typing import Any

import pulse as ps
from pulse_mantine import (
	Button,
	Card,
	Code,
	Container,
	Divider,
	Group,
	MantineProvider,
	Notifications,
	Stack,
	Text,
	Title,
	notifications,
)
from pulse_mantine.core.feedback.notifications import NotificationData


class NotificationsDemoState(ps.State):
	_counter: int

	def __init__(self) -> None:
		self._counter = 0

	def _next_payload(
		self, prefix: str, *, sticky: bool = False, **props: object
	) -> dict[str, Any]:
		self._counter += 1
		payload: dict[str, object] = {
			"title": f"{prefix} #{self._counter}",
			"message": f"Triggered from Python (#{self._counter})",
			"autoClose": False if sticky else 4000,
		}
		payload.update(props)
		return payload

	def show_basic(self) -> None:
		notifications.show(**self._next_payload("Notification", color="blue"))

	def show_sticky(self) -> None:
		notifications.show(
			**self._next_payload(
				"Persistent task",
				sticky=True,
				color="orange",
				withCloseButton=True,
			)
		)

	def update_last(self) -> None:
		visible = notifications.getVisible()
		if not visible:
			return
		# Update the most recently visible notification
		last = visible[-1]
		notifications.update(
			id=last["id"],
			title="Task complete",
			message="notifications.update(...) was invoked",
			color="teal",
			icon="✔",
		)

	def hide_last(self) -> None:
		visible = notifications.getVisible()
		if not visible:
			return
		# Hide the most recently visible notification
		notifications.hide(visible[-1]["id"])

	def enqueue_batch(self) -> None:
		for _ in range(6):
			notifications.show(
				**self._next_payload(
					"Queued",
					sticky=True,
					color="grape",
					withCloseButton=True,
				)
			)

	def clean_queue(self) -> None:
		notifications.cleanQueue()

	def clean_all(self) -> None:
		notifications.clean()

	def mark_all_success(self) -> None:
		def transform(existing: list[NotificationData]) -> list[NotificationData]:
			result: list[NotificationData] = []
			for index, item in enumerate(existing, start=1):
				result.append(
					{
						**item,
						"title": f"Completed #{index}",
						"message": "Updated via notifications.updateState",
						"color": "green",
						"autoClose": False,
					}
				)
			return result

		notifications.updateState(transform)

	def reverse_order(self) -> None:
		notifications.updateState(lambda current: list(reversed(current)))


@ps.component
def NotificationsDemo():
	state = ps.states(NotificationsDemoState)
	visible = notifications.getVisible()
	queued = notifications.getQueued()
	snapshot = notifications.getState()
	visible_count = len(visible)
	queue_count = len(queued)
	snapshot_json = json.dumps(snapshot, indent=2, default=str)

	return MantineProvider(
		Notifications(limit=3, position="top-right"),
		Container(size="sm", py="xl")[
			Stack(gap="lg")[
				Title(order=2)["Mantine notifications from Pulse"],
				Text(
					"These controls exercise the notifications wrapper. Try combining actions to"
					" verify show/update/hide, queue handling, and bulk state updates."
				),
				Card(withBorder=True, shadow="sm", padding="lg")[
					Stack(gap="sm")[
						Title(order=4)["Imperative API"],
						Group(gap="sm")[
							Button("Show notification", onClick=state.show_basic),
							Button("Show persistent", onClick=state.show_sticky),
							Button(
								"Update last",
								onClick=state.update_last,
								disabled=len(visible) == 0,
							),
							Button(
								"Hide last",
								onClick=state.hide_last,
								disabled=len(visible) == 0,
							),
						],
						Divider(),
						Title(order=4)["Queue management"],
						Group(gap="sm")[
							Button("Enqueue batch", onClick=state.enqueue_batch),
							Button("Clean queue", onClick=state.clean_queue),
							Button("Clean all", onClick=state.clean_all),
						],
						Divider(),
						Title(order=4)["Bulk transforms"],
						Group(gap="sm")[
							Button("Mark all success", onClick=state.mark_all_success),
							Button("Reverse order", onClick=state.reverse_order),
						],
					],
				],
				Card(withBorder=True, shadow="sm", padding="lg")[
					Stack(gap="xs")[
						Title(order=4)["Backend snapshot"],
						Text(f"Visible: {visible_count} · Queue: {queue_count}"),
						Code(block=True, style={"whiteSpace": "pre-wrap"})[
							snapshot_json
						],
					],
				],
			],
		],
	)


app = ps.App([ps.Route("/", NotificationsDemo)])
