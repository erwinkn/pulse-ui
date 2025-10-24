"""
Interactive demo showcasing State.drain / State.hydrate support.

This example keeps an active ProfileState instance on the page, allows the user
to mutate it, drains the state into a serializable payload, and later hydrates
archived payloads to verify that fields, preserved query results, and private
post-init data round-trip correctly.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from functools import partial
from typing import Any, override

import pulse as ps


class ProfileState(ps.State):
	"""State with queries, private attributes, and migrations."""

	__version__: int = 2

	user_id: int = 1
	visits: int = 1
	nickname: str | None = None
	secret_note: str = "Pulse user"
	_post_initialized_at: str | None = None
	_secret_token: str = ""

	def __init__(self, *, user_id: int = 1, nickname: str | None = None):
		self.user_id = user_id
		self.nickname = nickname

	def __post_init__(self):
		now = datetime.now(UTC).isoformat(timespec="seconds")
		self._post_initialized_at = now
		self._secret_token = f"token-{self.user_id}-{now}"

	def log_visit(self):
		self.visits += 1

	@ps.query(preserve=True)
	async def profile(self) -> dict[str, Any]:
		# Simulate a fetch; preserving results lets hydration restore cached data.
		await asyncio.sleep(0.05)
		return {
			"id": self.user_id,
			"nickname": self.nickname or "anonymous",
			"visits": self.visits,
			"note": self.secret_note,
		}

	@profile.key
	def _profile_key(self):
		return ("profile", self.user_id)

	@ps.query()
	async def last_refreshed(self) -> str:
		# This query intentionally does NOT preserve results. After hydration it
		# will begin loading again instead of restoring stale timestamps.
		await asyncio.sleep(0.05)
		return datetime.now(UTC).isoformat(timespec="seconds")

	@override
	@classmethod
	def __migrate__(
		cls,
		start_version: int,
		target_version: int,
		values: dict[str, Any],
	) -> dict[str, Any]:
		if start_version == 1 and target_version == 2:
			values.setdefault("nickname", None)
			values.setdefault("secret_note", "Pulse user")
			return values
		raise ValueError(
			f"{cls.__name__} cannot migrate from version {start_version} to "
			+ f"{target_version}"
		)


class SnapshotArchiveState(ps.State):
	"""Keeps a list of drained payloads and the most recent hydration preview."""

	snapshots: list[dict[str, Any]] = []
	hydrated_summary: dict[str, Any] | None = None
	_next_id: int = 1

	def append_snapshot(self, payload: dict[str, Any]):
		entry = {
			"id": self._next_id,
			"stored_at": datetime.now(UTC).isoformat(timespec="seconds"),
			"payload": payload,
		}
		self.snapshots = [entry, *self.snapshots]
		self._next_id += 1
		# Reset hydration preview so the UI reflects the latest archive
		self.hydrated_summary = None

	def hydrate_snapshot(self, snapshot_id: int):
		for entry in self.snapshots:
			if entry["id"] == snapshot_id:
				payload = entry["payload"]
				rehydrated = ProfileState.__new__(ProfileState).hydrate(payload)
				summary = {
					"user_id": rehydrated.user_id,
					"visits": rehydrated.visits,
					"nickname": rehydrated.nickname,
					"secret_note": rehydrated.secret_note,
					"_secret_token": rehydrated._secret_token,  # pyright: ignore[reportPrivateUsage]
					"_post_initialized_at": rehydrated._post_initialized_at,  # pyright: ignore[reportPrivateUsage]
					"profile_has_loaded": rehydrated.profile.has_loaded,
					"profile_data": rehydrated.profile.data,
					"last_refreshed_has_loaded": rehydrated.last_refreshed.has_loaded,
					"last_refreshed_is_loading": rehydrated.last_refreshed.is_loading,
				}
				self.hydrated_summary = summary
				return


def _render_summary(summary: dict[str, Any]) -> ps.Node:
	rows: list[ps.Element] = []
	for key, value in summary.items():
		if isinstance(value, dict):
			value_text = json.dumps(value, indent=2)
		else:
			value_text = json.dumps(value, default=str)
		rows.append(
			ps.tr(
				ps.th(key, className="text-left align-top pr-3 font-semibold"),
				ps.td(
					ps.pre(value_text, className="text-xs bg-gray-100 p-2 rounded"),
					className="align-top",
				),
			)
		)
	return ps.table(
		ps.tbody(*rows),
		className="w-full text-sm border border-gray-200 rounded overflow-hidden",
	)


@ps.component
def state_persistence_demo():
	profile, archive = ps.states(ProfileState, SnapshotArchiveState)

	def increment_visits():
		profile.log_visit()

	def randomize_user():
		new_id = profile.user_id + 1
		profile.user_id = new_id
		profile.nickname = f"User {new_id}"

	def drain_snapshot():
		archive.append_snapshot(profile.drain())

	def hydrate_snapshot(snapshot_id: int):
		archive.hydrate_snapshot(snapshot_id)

	content = [
		ps.section(
			ps.h1(
				"State Drain & Hydrate Demo",
				className="text-3xl font-bold mb-2",
			),
			ps.p(
				"Mutate the active profile state, archive snapshots via drain(), "
				+ "and hydrate them later to verify preserved query results and "
				+ "post-init hooks.",
				className="text-gray-600",
			),
			className="border-b border-gray-200 pb-4",
		),
		ps.section(
			ps.h2("Active ProfileState", className="text-2xl font-semibold"),
			ps.div(
				ps.p(f"user_id: {profile.user_id}"),
				ps.p(f"visits: {profile.visits}"),
				ps.p(f"nickname: {profile.nickname or '—'}"),
				ps.p(f"secret_note: {profile.secret_note}"),
				ps.div(
					ps.button("Increment visits", onClick=increment_visits),
					ps.button(
						"Change user",
						onClick=randomize_user,
						className="ml-2",
					),
					ps.button(
						"Drain snapshot",
						onClick=drain_snapshot,
						className="ml-2 btn-primary",
					),
					className="mt-3 space-x-2",
				),
				className="space-y-1",
			),
			ps.div(
				ps.h3("Query status", className="font-semibold mt-4"),
				ps.p(
					f"profile.has_loaded = {profile.profile.has_loaded}, "
					+ f"last_refreshed.has_loaded = {profile.last_refreshed.has_loaded}",
					className="text-sm text-gray-600",
				),
			),
			className="bg-gray-50 p-4 rounded shadow-inner",
		),
		ps.section(
			ps.h2("Stored Snapshots", className="text-2xl font-semibold"),
			ps.p(
				"Snapshots capture the drain() payload, including preserved query "
				+ "results. Hydrate any snapshot to inspect the reconstructed state.",
				className="text-gray-600 mb-3",
			),
			ps.ul(
				*[
					ps.li(
						ps.div(
							ps.div(
								ps.span(
									f"Snapshot #{entry['id']} ",
									className="font-semibold",
								),
								ps.span(
									f"stored_at={entry['stored_at']}",
									className="text-xs text-gray-500",
								),
							),
							ps.pre(
								json.dumps(entry["payload"], indent=2),
								className="bg-gray-900 text-green-200 text-xs p-3 rounded mt-2 overflow-auto",
							),
							ps.button(
								"Hydrate snapshot",
								onClick=partial(hydrate_snapshot, entry["id"]),
								className="mt-2",
							),
							className="bg-white border border-gray-200 rounded p-3 shadow-sm",
						),
						className="mb-4",
					)
					for entry in archive.snapshots
				],
				className="list-none p-0",
			),
			className="bg-gray-50 p-4 rounded shadow-inner",
		),
		ps.section(
			ps.h2("Hydrated Snapshot Preview", className="text-2xl font-semibold"),
			ps.p(
				"Hydrate restores preserved query caches while allowing "
				+ "non-preserved queries to resume loading. Private fields set in "
				+ "__post_init__ update during hydration, confirmed below.",
				className="text-gray-600 mb-3",
			),
			(
				_render_summary(archive.hydrated_summary)
				if archive.hydrated_summary
				else ps.div(
					"No snapshot hydrated yet.",
					className="text-sm text-gray-500",
				)
			),
			className="bg-gray-50 p-4 rounded shadow-inner",
		),
	]

	return ps.div(*content, className="space-y-6 p-6 bg-white max-w-4xl mx-auto")


app = ps.App(
	routes=[
		ps.Route("/", state_persistence_demo),
	],
)
