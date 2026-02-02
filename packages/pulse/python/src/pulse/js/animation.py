"""
Web Animations API builtins.

Usage:

```python
from pulse.js import Animation, KeyframeEffect, document, obj

@ps.javascript
def example(target):
    effect = KeyframeEffect(
        target,
        [obj(transform="translateX(0px)"), obj(transform="translateX(100px)")],
        obj(duration=300, easing="ease-in-out"),
    )
    animation = Animation(effect, document.timeline)
    animation.play()
```
"""

from __future__ import annotations

from typing import Any as _Any
from typing import TypedDict as _TypedDict
from typing import overload as _overload

from pulse.js._types import Element as _Element
from pulse.js.promise import Promise as _Promise
from pulse.transpiler.js_module import JsModule

Keyframe = dict[str, _Any]
ComputedKeyframe = dict[str, _Any]
PropertyIndexedKeyframes = dict[str, _Any]


class EffectTiming(_TypedDict, total=False):
	delay: float
	direction: str
	duration: float | str
	easing: str
	endDelay: float
	fill: str
	iterations: float
	iterationStart: float


class OptionalEffectTiming(_TypedDict, total=False):
	delay: float
	direction: str
	duration: float | str
	easing: str
	endDelay: float
	fill: str
	iterations: float
	iterationStart: float


class KeyframeEffectOptions(EffectTiming, total=False):
	composite: str
	iterationComposite: str
	pseudoElement: str


class ComputedEffectTiming(EffectTiming, total=False):
	endTime: float
	activeDuration: float
	localTime: float | None
	progress: float | None
	currentIteration: float | None


class DocumentTimelineOptions(_TypedDict, total=False):
	originTime: float


class KeyframeEffect:
	"""Keyframe-based animation effect."""

	@_overload
	def __init__(
		self,
		target: _Element | None,
		keyframes: list[Keyframe] | PropertyIndexedKeyframes | None = None,
		options: float | int | KeyframeEffectOptions | None = None,
		/,
	) -> None: ...

	@_overload
	def __init__(self, source: "KeyframeEffect", /) -> None: ...

	def __init__(
		self,
		target: _Element | None | KeyframeEffect,
		keyframes: list[Keyframe] | PropertyIndexedKeyframes | None = None,
		options: float | int | KeyframeEffectOptions | None = None,
		/,
	) -> None: ...

	@property
	def target(self) -> _Element | None: ...

	@property
	def pseudoElement(self) -> str | None: ...

	@property
	def iterationComposite(self) -> str: ...

	@property
	def composite(self) -> str: ...

	def getComputedTiming(self) -> ComputedEffectTiming: ...

	def getKeyframes(self) -> list[ComputedKeyframe]: ...

	def getTiming(self) -> EffectTiming: ...

	def setKeyframes(
		self,
		keyframes: list[Keyframe] | PropertyIndexedKeyframes | None,
		/,
	) -> None: ...

	def updateTiming(self, timing: OptionalEffectTiming, /) -> None: ...


class Animation:
	"""Playback controller for a KeyframeEffect."""

	def __init__(
		self,
		effect: KeyframeEffect | _Any | None = None,
		timeline: DocumentTimeline | _Any | None = None,
		/,
	) -> None: ...

	@property
	def currentTime(self) -> float | None: ...

	@currentTime.setter
	def currentTime(self, value: float | None) -> None: ...

	@property
	def effect(self) -> _Any | None: ...

	@effect.setter
	def effect(self, value: _Any | None) -> None: ...

	@property
	def finished(self) -> _Promise[_Any]: ...

	@property
	def id(self) -> str: ...

	@id.setter
	def id(self, value: str) -> None: ...

	@property
	def overallProgress(self) -> float: ...

	@property
	def pending(self) -> bool: ...

	@property
	def playState(self) -> str: ...

	@property
	def playbackRate(self) -> float: ...

	@playbackRate.setter
	def playbackRate(self, value: float) -> None: ...

	@property
	def ready(self) -> _Promise[_Any]: ...

	@property
	def replaceState(self) -> str: ...

	@property
	def startTime(self) -> float | None: ...

	@startTime.setter
	def startTime(self, value: float | None) -> None: ...

	@property
	def timeline(self) -> _Any | None: ...

	@timeline.setter
	def timeline(self, value: _Any | None) -> None: ...

	def cancel(self) -> None: ...

	def commitStyles(self) -> None: ...

	def finish(self) -> None: ...

	def pause(self) -> None: ...

	def persist(self) -> None: ...

	def play(self) -> None: ...

	def reverse(self) -> None: ...

	def updatePlaybackRate(self, rate: float, /) -> None: ...


class DocumentTimeline:
	"""Timeline associated with a document."""

	def __init__(self, options: DocumentTimelineOptions | None = None, /) -> None: ...

	@property
	def currentTime(self) -> float | None: ...


# Self-register this module as a JS builtin (global identifiers)
JsModule.register(name=None)
