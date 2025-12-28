from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable, Mapping
from typing import Any, Literal, NotRequired, Required, Self, TypedDict, Unpack, cast
from uuid import uuid4

import pulse as ps

from ..box import BoxProps
from ..styles import StyleFn
from ..theme import MantineRadius
from ..types import MantineColor

ps.Import("", "@mantine/notifications/styles.css", kind="side_effect")


NotificationRootCSSVariables = Literal["--notification-radius", "--notification-color"]
NotificationStylesNames = Literal[
	"root",
	"icon",
	"loader",
	"body",
	"title",
	"description",
	"closeButton",
]
NotificationAttributes = dict[NotificationStylesNames, dict[str, Any]]
NotificationStyles = dict[NotificationStylesNames, ps.CSSProperties]
NotificationClassNames = dict[NotificationStylesNames, str]


class NotificationCssVariables(TypedDict, total=False):
	root: dict[NotificationRootCSSVariables, str]


class NotificationProps(  # pyright: ignore[reportIncompatibleVariableOverride]
	ps.HTMLDivProps,
	BoxProps,
	total=False,
):
	variant: str
	"""Component variant"""
	onClose: ps.EventHandler0
	"""Called when the close button is clicked"""
	color: MantineColor
	"""Controls notification line or icon color"""
	radius: MantineRadius
	"""Controls notification border radius"""
	icon: ps.Element
	"""Notification icon, replaces color line"""
	title: ps.Element  # pyright: ignore[reportIncompatibleVariableOverride]
	"""Notification title, displayed above the message body"""
	loading: bool
	"""If set, the Loader component is displayed instead of the icon"""
	withBorder: bool
	"""Adds border to the root element"""
	withCloseButton: bool
	"""If set, the close button is visible"""
	closeButtonProps: Mapping[str, Any]
	"""Props passed down to the close button"""
	loaderProps: Mapping[str, Any]
	"""Props passed down to the Loader component"""

	# Styles API props
	unstyled: bool
	"""Removes default styles from the component"""
	classNames: (
		NotificationClassNames | StyleFn[NotificationProps, Any, NotificationClassNames]
	)
	"""Additional class names passed to elements"""
	styles: NotificationStyles | StyleFn[NotificationProps, Any, NotificationStyles]
	"""Additional styles passed to elements"""
	vars: StyleFn[NotificationProps, Any, NotificationCssVariables]
	"""CSS variables for the component"""
	attributes: NotificationAttributes
	"""Additional attributes passed to elements"""


@ps.react_component(ps.Import("Notification", "@mantine/core"))
def Notification(
	*children: ps.Node, key: str | None = None, **props: Unpack[NotificationProps]
): ...


NotificationsStylesNames = Literal["root", "notification"]
NotificationsAttributes = dict[NotificationsStylesNames, dict[str, Any]]
NotificationsStyles = dict[NotificationsStylesNames, ps.CSSProperties]
NotificationsClassNames = dict[NotificationsStylesNames, str]


class NotificationsCssVariables(TypedDict, total=False):
	root: dict[
		Literal["--notifications-z-index", "--notifications-container-width"],
		str,
	]


class NotificationsProps(  # pyright: ignore[reportIncompatibleVariableOverride]
	ps.HTMLDivProps,
	BoxProps,
	total=False,
):
	position: NotificationPosition
	"""Notifications default position"""
	autoClose: int | bool
	"""Auto close timeout for all notifications in ms, `False` to disable auto close"""
	transitionDuration: int
	"""Notification transition duration in ms"""
	containerWidth: int | str
	"""Notification width, cannot exceed 100%"""
	notificationMaxHeight: int | str
	"""Notification max-height, used for transitions"""
	limit: int
	"""Maximum number of notifications displayed at a time"""
	zIndex: int | str
	"""Notifications container z-index"""
	portalProps: Mapping[str, Any]
	"""Props passed down to the Portal component"""
	withinPortal: bool
	"""Determines whether notifications container should be rendered inside Portal"""

	# Styles API props
	unstyled: bool
	"""Removes default styles from the component"""
	classNames: (
		NotificationsClassNames
		| StyleFn[NotificationsProps, Any, NotificationsClassNames]
	)
	"""Additional class names passed to elements"""
	styles: NotificationsStyles | StyleFn[NotificationsProps, Any, NotificationsStyles]
	"""Additional styles passed to elements"""
	vars: StyleFn[NotificationsProps, Any, NotificationsCssVariables]
	"""CSS variables for the component"""
	attributes: NotificationsAttributes
	"""Additional attributes passed to elements"""


NotificationPosition = Literal[
	"top-left",
	"top-right",
	"top-center",
	"bottom-left",
	"bottom-right",
	"bottom-center",
]


class NotificationDataWithoutId(NotificationProps, total=False):
	id: str
	"""Notification id, can be used to close or update notification"""
	message: Required[str]
	"""Main notification message. Real API also supports nodes, but we can't handle that yet."""
	position: NotificationPosition
	"""Notification position"""
	autoClose: int | bool
	"""Per-notification auto close timeout"""
	onClose: Callable[[Self], None]
	"""Called when notification closes"""
	onOpen: Callable[[Self], None]
	"""Called when notification opens"""


class NotificationData(NotificationDataWithoutId):
	id: str  # pyright: ignore[reportGeneralTypeIssues]
	onClose: NotRequired[Callable[[Self], None]]
	"""Called when notification closes"""
	onOpen: NotRequired[Callable[[Self], None]]
	"""Called when notification opens"""


@ps.react_component(ps.Import("Notifications", "pulse-mantine"))
def NotificationsInternal(
	*children: ps.Node,
	key: str | None = None,
	channelId: str | None = None,
	**props: Unpack[NotificationsProps],
): ...


NOTIFICATIONS_CHANNEL_ID = uuid.uuid4().hex


class NotificationsStore(ps.State):
	_channel: ps.Channel
	registry: dict[str, NotificationData]
	visible_ids: list[str]
	queued_ids: list[str]

	def __init__(self) -> None:
		self._channel = ps.channel(NOTIFICATIONS_CHANNEL_ID)
		self.registry = {}
		self.visible_ids = []
		self.queued_ids = []
		self._channel.on("stateSync", self._on_state_sync)

	def show(self, kwargs: NotificationDataWithoutId) -> str:
		ident, payload = ensure_id(kwargs)
		existing = self.registry.get(ident)
		merged = payload if not existing else existing | payload
		self.registry[ident] = merged
		self._channel.emit("show", serialize(merged))
		return ident

	def update(self, kwargs: NotificationData) -> str:
		ident = kwargs["id"]
		payload = kwargs
		existing = self.registry.get(ident)
		merged = payload if not existing else existing | payload
		self.registry[ident] = merged
		self._channel.emit("update", serialize(merged))
		return ident

	def hide(self, id: str) -> str:
		self._channel.emit("hide", {"id": id})
		return id

	def clean(self) -> None:
		self._channel.emit("clean")

	def cleanQueue(self) -> None:
		self._channel.emit("cleanQueue")

	def getVisible(self) -> list[NotificationData]:
		return [self.registry[id_] for id_ in self.visible_ids]

	def getQueued(self) -> list[NotificationData]:
		return [self.registry[id_] for id_ in self.queued_ids]

	def getState(self) -> list[NotificationData]:
		return self.getVisible() + self.getQueued()

	def isVisible(self, id: str) -> bool:
		return id in self.visible_ids

	def isQueued(self, id: str) -> bool:
		return id in self.queued_ids

	def updateState(
		self,
		update: Callable[[list[NotificationData]], Iterable[NotificationData]]
		| Iterable[NotificationData],
	) -> None:
		current = self.getState()
		if callable(update):
			result = update(current)
		else:
			result = update
		new_notifications: list[NotificationData] = []
		for item in result:
			ident, item = ensure_id(item)
			self.registry[ident] = item
			new_notifications.append(item)
		self._channel.emit(
			"updateState",
			{"notifications": [serialize(x) for x in new_notifications]},
		)

	def _on_state_sync(self, payload: Any) -> None:
		if not isinstance(payload, dict):
			return
		visible = cast(list[str], payload["notifications"])
		queue = cast(list[str], payload["queue"])

		# Create sets once to avoid repeated conversions
		current_visible = set(visible)
		current_queue = set(queue)
		current_ids = current_visible | current_queue
		registry_keys = set(self.registry.keys())
		previous_visible = set(self.visible_ids)
		previous_queue = set(self.queued_ids)
		previous_ids = previous_visible | previous_queue

		# Error if we receive IDs that are not in the registry
		unknown_ids = current_ids - registry_keys
		if unknown_ids:
			raise ValueError(f"Received unknown notification IDs: {unknown_ids}")

		# Determine newly opened and closed IDs
		newly_opened = current_visible - previous_visible
		closed_ids = previous_ids - current_ids

		# Call onOpen handlers for newly opened IDs (only when they appear in visible)
		for ident in newly_opened:
			notification = self.registry[ident]
			if "onOpen" in notification and callable(notification["onOpen"]):
				notification["onOpen"](notification)

		# Call onClose handlers for closed IDs
		for ident in closed_ids:
			notification = self.registry[ident]
			if "onClose" in notification and callable(notification["onClose"]):
				notification["onClose"](notification)
			# Remove closed notifications from the registry
			self.registry.pop(ident, None)

		# Update the current state
		self.visible_ids = visible
		self.queued_ids = queue


def Notifications(
	*children: ps.Node,
	key: str | None = None,
	**props: Unpack[NotificationsProps],
):
	return NotificationsInternal(
		*children,
		key=key,
		**props,
		channelId=NOTIFICATIONS_CHANNEL_ID,
	)


def ensure_id(
	value: NotificationDataWithoutId | NotificationData,
) -> tuple[str, NotificationData]:
	if not isinstance(value, Mapping):
		raise TypeError("Notification payload must be a mapping")
	ident = value.get("id")
	if not ident:
		ident = uuid4().hex
		value["id"] = ident
	return ident, cast(NotificationData, value)


def serialize(value: NotificationData):
	return {k: v for k, v in value.items() if k not in ("onClose", "onOpen")}


notifications_state = ps.global_state(NotificationsStore)


class NotificationsApi:
	__slots__: tuple[()] = ()

	def _resolve(self) -> NotificationsStore:
		return notifications_state()

	def show(self, **payload: Unpack[NotificationDataWithoutId]):
		return self._resolve().show(payload)

	def update(self, **payload: Unpack[NotificationData]):
		return self._resolve().update(payload)

	def hide(self, id: str):
		return self._resolve().hide(id)

	def clean(self) -> None:
		self._resolve().clean()

	def cleanQueue(self) -> None:
		self._resolve().cleanQueue()

	def updateState(
		self,
		update: Callable[[list[NotificationData]], Iterable[NotificationData]]
		| Iterable[NotificationData],
	) -> None:
		self._resolve().updateState(update)

	def getVisible(self):
		return self._resolve().getVisible()

	def getQueued(self):
		return self._resolve().getQueued()

	def getState(self):
		return self._resolve().getState()

	def isVisible(self, id: str) -> bool:
		return self._resolve().isVisible(id)

	def isQueued(self, id: str) -> bool:
		return self._resolve().isQueued(id)


notifications = NotificationsApi()
