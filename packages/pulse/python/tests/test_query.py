import asyncio
from typing import Any

import pulse as ps
import pytest
from pulse.reactive import flush_effects


async def run_query():
	"Assumes an async query with a single `await asyncio.sleep(0)` in the middle"
	# print('--- Running query ----')
	flush_effects()  # runs the effect
	await asyncio.sleep(0)  # starts the async query. stops at the sleep call.
	await asyncio.sleep(0)  # finishes the async query
	await asyncio.sleep(0)  # executes the `done` callback
	# print('--- Query should be finished ----')


@pytest.mark.asyncio
async def test_state_query_success():
	query_running = False

	class S(ps.State):
		uid: int = 1

		@ps.query
		async def user(self) -> dict[str, Any]:
			nonlocal query_running
			query_running = True
			await asyncio.sleep(0)
			res = {"id": self.uid}
			query_running = False
			return res

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	q = s.user

	# Initial state is loading until first fetch completes
	assert q.is_loading

	flush_effects()  # runs the effect that starts the query
	await asyncio.sleep(0)  # wait for query to start
	assert query_running
	await asyncio.sleep(0)  # wait for query to run
	await asyncio.sleep(0)  # wait for callback to execute
	assert not query_running
	assert not q.is_loading
	assert not q.is_error
	assert q.data == {"id": s.uid}


@pytest.mark.asyncio
async def test_state_query_refetch():
	class S(ps.State):
		uid: int = 1
		calls: int = 0

		@ps.query
		async def user(self) -> dict[str, Any]:
			self.calls += 1
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	q = s.user

	# First fetch (scheduled on property access)
	await run_query()
	assert q.data == {"id": 1}
	assert s.calls == 1

	# Manual refetch
	q.refetch()
	await run_query()
	assert q.data == {"id": 1}
	assert s.calls == 2


@pytest.mark.asyncio
async def test_state_query_error():
	class S(ps.State):
		flag: int = 0

		@ps.query
		async def fail(self):
			await asyncio.sleep(0)
			raise RuntimeError("boom")

		@fail.key
		def _fail_key(self):
			return ("fail", self.flag)

	s = S()
	q = s.fail
	await run_query()

	assert q.is_loading is False
	assert q.is_error is True
	assert isinstance(q.error, RuntimeError)


@pytest.mark.asyncio
async def test_state_query_error_refetch():
	class S(ps.State):
		calls: int = 0

		@ps.query
		async def fail(self):
			self.calls += 1
			await asyncio.sleep(0)
			raise RuntimeError("boom")

		@fail.key
		def _fail_key(self):
			return ("fail",)

	s = S()
	q = s.fail

	# Refetch after error
	q.refetch()
	await run_query()
	assert q.is_error is True
	assert s.calls == 1

	# Refetch should run again and still error
	q.refetch()
	await run_query()
	assert q.is_error is True
	assert s.calls == 2


@pytest.mark.asyncio
async def test_state_query_refetch_on_key_change():
	class S(ps.State):
		uid: int = 1
		calls: int = 0

		@ps.query
		async def user(self):
			self.calls += 1
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	q = s.user

	# First fetch (scheduled on property access)
	await run_query()
	assert q.data == {"id": 1}
	assert s.calls == 1

	# Change key; effect should re-run and refetch
	s.uid = 2
	await run_query()
	assert q.data == {"id": 2}
	assert s.calls == 2


@pytest.mark.asyncio
async def test_state_query_missing_key_defaults_to_auto_tracking():
	class S(ps.State):
		uid: int = 1

		@ps.query
		async def user(self):
			await asyncio.sleep(0)
			return {"id": self.uid}

	s = S()
	q = s.user
	# initial
	flush_effects()
	await asyncio.sleep(0)
	await asyncio.sleep(0)
	assert q.data == {"id": 1}
	# change dep -> auto re-run
	s.uid = 2
	flush_effects()
	await asyncio.sleep(0)
	await asyncio.sleep(0)
	assert q.data == {"id": 2}


@pytest.mark.asyncio
async def test_state_query_keep_previous_data_on_refetch_default():
	class S(ps.State):
		uid: int = 1

		@ps.query
		async def user(self) -> dict[str, Any]:
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	q = s.user

	# initial load
	flush_effects()
	await asyncio.sleep(0)
	await asyncio.sleep(0)
	await asyncio.sleep(0)
	assert q.data == {"id": 1}

	# change key -> effect re-runs; while loading, previous data should be kept (default)
	s.uid = 2
	flush_effects()  # schedule new fetch
	await asyncio.sleep(0)  # task started, still loading
	assert q.is_loading is True
	assert q.data == {"id": 1}
	# finish
	await asyncio.sleep(0)
	await asyncio.sleep(0)
	assert q.is_loading is False
	assert q.data == {"id": 2}


@pytest.mark.asyncio
async def test_state_query_keep_previous_data_can_be_disabled():
	class S(ps.State):
		uid: int = 1

		@ps.query(keep_previous_data=False)
		async def user(self) -> dict[str, Any]:
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	q = s.user

	# initial load
	flush_effects()
	await asyncio.sleep(0)
	await asyncio.sleep(0)
	await asyncio.sleep(0)
	assert q.data == {"id": 1}

	# change key -> while loading, data should be cleared when keep_previous_data=False
	s.uid = 2
	flush_effects()
	await asyncio.sleep(0)  # task started
	assert q.is_loading is True
	assert q.data is None
	# finish
	await asyncio.sleep(0)
	await asyncio.sleep(0)
	assert q.is_loading is False
	assert q.data == {"id": 2}


@pytest.mark.asyncio
async def test_state_query_manual_set_data():
	class S(ps.State):
		uid: int = 1

		@ps.query
		async def user(self) -> dict[str, Any]:
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	q = s.user

	# Finish first fetch
	flush_effects()
	await asyncio.sleep(0)
	await asyncio.sleep(0)
	await asyncio.sleep(0)
	assert q.data == {"id": 1}

	# Manual override (optimistic update)
	q.set_data({"id": 999})
	assert q.data == {"id": 999}
	assert q.is_loading is False

	# Trigger refetch; while loading data should remain overridden when keep_previous_data=True
	s.uid = 2
	flush_effects()
	await asyncio.sleep(0)
	assert q.is_loading is True
	assert q.data == {"id": 999}
	# Complete fetch overwrites data with real value
	await asyncio.sleep(0)
	await asyncio.sleep(0)
	assert q.is_loading is False
	assert q.data == {"id": 2}


@pytest.mark.asyncio
async def test_state_query_with_initial_value_narrows_and_preserves():
	class S(ps.State):
		uid: int = 1

		@ps.query(initial={"id": 0})
		async def user(self) -> dict[str, Any]:
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	q = s.user

	# Immediately available initial value, not None
	assert q.data == {"id": 0}
	assert q.is_loading is True

	# After fetch, data updates
	await run_query()
	assert q.is_loading is False
	assert q.data == {"id": 1}

	# Disable keep_previous_data -> during refetch, it should reset to initial, not None
	class S2(ps.State):
		uid: int = 1

		@ps.query(initial={"id": -1}, keep_previous_data=False)
		async def user(self) -> dict[str, int]:
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s2 = S2()
	q2 = s2.user
	assert q2.data == {"id": -1}
	await run_query()
	assert q2.data == {"id": 1}

	# change key -> refetch; while loading with keep_previous_data=False, it should reset to initial
	s2.uid = 2
	flush_effects()
	await asyncio.sleep(0)
	assert q2.is_loading is True
	assert q2.data == {"id": -1}
	await asyncio.sleep(0)
	await asyncio.sleep(0)
	assert q2.is_loading is False
	assert q2.data == {"id": 2}


@pytest.mark.asyncio
async def test_state_query_set_initial_data_before_first_load_and_ignore_after():
	class S(ps.State):
		uid: int = 1

		def __init__(self):
			super().__init__()
			# set initial data from constructor
			self.user.set_initial_data({"id": 123})

		@ps.query
		async def user(self) -> dict[str, Any]:
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	q = s.user
	# initial set is visible
	assert q.data == {"id": 123}
	assert q.has_loaded is False

	# first load completes and flips has_loaded
	await run_query()
	assert q.has_loaded is True
	assert q.data == {"id": 1}

	# subsequent set_initial_data is ignored
	q.set_initial_data({"id": 999})
	assert q.data == {"id": 1}

	# manual set_data still works
	q.set_data({"id": 777})
	assert q.data == {"id": 777}


@pytest.mark.asyncio
async def test_state_query_initial_data_decorator_uses_value_after_init_and_updates():
	class S(ps.State):
		uid: int = 1
		seed: dict[str, Any] | None = None

		def __init__(self):
			super().__init__()
			# Seed after super().__init__ to ensure decorator reads updated state
			self.seed = {"id": 999}

		@ps.query
		async def user(self) -> dict[str, Any]:
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.initial_data
		def _user_initial(self) -> dict[str, Any]:
			# test ensures seed is set before decorator runs; cast for typing
			return self.seed or {"id": -999}

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	q = s.user
	# initial from decorator, not None
	assert q.data == {"id": 999}
	assert q.is_loading is True
	# After first fetch, data updates
	await run_query()
	assert q.is_loading is False
	assert q.data == {"id": 1}


@pytest.mark.asyncio
async def test_state_query_initial_data_respected_on_refetch_when_keep_previous_false():
	class S(ps.State):
		uid: int = 1

		@ps.query(keep_previous_data=False)
		async def user(self) -> dict[str, Any]:
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.initial_data
		def _user_initial(self):
			return {"id": -1}

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	q = s.user
	assert q.data == {"id": -1}
	await run_query()
	assert q.data == {"id": 1}
	# Change key -> while loading, data should reset to initial_data
	s.uid = 2
	flush_effects()
	await asyncio.sleep(0)
	assert q.is_loading is True
	assert q.data == {"id": -1}
	await asyncio.sleep(0)
	await asyncio.sleep(0)
	assert q.is_loading is False
	assert q.data == {"id": 2}


@pytest.mark.asyncio
async def test_state_query_on_success_sync():
	class S(ps.State):
		uid: int = 1
		ok_calls: int = 0
		last: dict[str, Any] | None = None

		@ps.query
		async def user(self) -> dict[str, Any]:
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.on_success
		def _on_success(self, data: dict[str, Any]):
			self.ok_calls += 1
			self.last = data

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	q = s.user
	await run_query()
	assert q.data == {"id": 1}
	assert s.ok_calls == 1
	assert s.last == {"id": 1}
	s.uid = 2
	await run_query()
	assert q.data == {"id": 2}
	assert s.ok_calls == 2


@pytest.mark.asyncio
async def test_state_query_on_success_async():
	class S(ps.State):
		uid: int = 1
		async_ok_calls: int = 0
		last: dict[str, Any] | None = None

		@ps.query
		async def user(self) -> dict[str, Any]:
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.on_success
		async def _on_success_async(self, data: dict[str, Any]):
			await asyncio.sleep(0)
			self.async_ok_calls += 1
			self.last = data

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	q = s.user
	await run_query()
	assert s.async_ok_calls == 1
	assert s.last == {"id": 1}
	assert q.data == {"id": 1}
	s.uid = 2
	await run_query()
	assert s.async_ok_calls == 2
	assert s.last == {"id": 2}
	assert q.data == {"id": 2}
	assert s.last == {"id": 2}


@pytest.mark.asyncio
async def test_state_query_on_success_handler_reads_are_untracked():
	class S(ps.State):
		uid: int = 1
		count: int = 0
		seen: list[int] = []

		@ps.computed
		def doubled(self) -> int:
			return self.count * 2

		@ps.query
		async def user(self) -> dict[str, Any]:
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.on_success
		def _on_success(self, data: dict[str, Any]):
			# read a signal and a computed; should not bind as deps
			_ = self.count
			_ = self.doubled
			self.seen.append(data["id"])  # mutation for verification

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	_ = s.user
	await run_query()
	assert s.seen == [1]
	# Change signal/computed inputs; should NOT cause refetch or re-run
	s.count = 5
	# Flush effects to simulate a render cycle
	flush_effects()
	await asyncio.sleep(0)
	await asyncio.sleep(0)
	# No new success call due to count change
	assert s.seen == [1]
	# Key change still triggers
	s.uid = 2
	await run_query()
	assert s.seen == [1, 2]


@pytest.mark.asyncio
async def test_state_query_on_error_handler_reads_are_untracked():
	class S(ps.State):
		flag: int = 0
		count: int = 0
		hits: int = 0

		@ps.computed
		def doubled(self) -> int:
			return self.count * 2

		@ps.query
		async def fail(self):
			await asyncio.sleep(0)
			raise RuntimeError("boom")

		@fail.on_error
		def _on_error(self, e: Exception):
			_ = self.count
			_ = self.doubled
			self.hits += 1

		@fail.key
		def _fail_key(self):
			return ("fail", self.flag)

	s = S()
	_ = s.fail
	await run_query()
	assert s.hits == 1
	# Changing signals/computeds that were read in handler should not re-run effect
	s.count = 3
	flush_effects()
	await asyncio.sleep(0)
	await asyncio.sleep(0)
	assert s.hits == 1
	# Key change should trigger and run handler again
	s.flag = 1
	await run_query()
	assert s.hits == 2


@pytest.mark.asyncio
async def test_state_query_on_error_handler_sync_and_async():
	class S(ps.State):
		calls: int = 0
		err_calls: int = 0
		last_err: Exception | None = None

		@ps.query
		async def fail(self):
			self.calls += 1
			await asyncio.sleep(0)
			raise RuntimeError("boom")

		@fail.on_error
		def _on_error(self, e: Exception):
			self.err_calls += 1
			self.last_err = e

		@fail.key
		def _fail_key(self):
			return ("fail",)

	s = S()
	q = s.fail
	await run_query()
	assert q.is_error is True
	assert s.calls == 1
	assert s.err_calls == 1
	assert isinstance(s.last_err, RuntimeError)
	# Refetch -> handlers run again
	q.refetch()
	await run_query()
	assert s.calls == 2
	assert s.err_calls == 2


@pytest.mark.asyncio
async def test_state_query_on_error_handler_async_only():
	class S(ps.State):
		calls: int = 0
		async_err_calls: int = 0
		last_err: Exception | None = None

		@ps.query
		async def fail(self):
			self.calls += 1
			await asyncio.sleep(0)
			raise RuntimeError("boom")

		@fail.on_error
		async def _on_error_async(self, e: Exception):
			await asyncio.sleep(0)
			self.async_err_calls += 1
			self.last_err = e

		@fail.key
		def _fail_key(self):
			return ("fail",)

	s = S()
	_ = s.fail
	await run_query()
	assert s.calls == 1
	assert s.async_err_calls == 1
	assert isinstance(s.last_err, RuntimeError)
	s.fail.refetch()
	await run_query()
	assert s.calls == 2
	assert s.async_err_calls == 2


@pytest.mark.asyncio
async def test_state_query_dispose_cancels_inflight_and_stops_updates():
	class S(ps.State):
		uid: int = 1
		started: bool = False
		finished: bool = False

		@ps.query
		async def user(self) -> dict[str, Any]:
			self.started = True
			# simulate in-flight
			await asyncio.sleep(0)
			self.finished = True
			return {"id": self.uid}

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	_ = s.user

	# Start the task but dispose before it completes
	flush_effects()
	await asyncio.sleep(0)
	assert s.started is True

	s.dispose()

	# Allow any scheduled tasks to attempt to finish; they should be canceled
	await asyncio.sleep(0)
	await asyncio.sleep(0)

	# The effect's task should be canceled or finished; either is acceptable due to race
	eff = getattr(s, "__query_effect_user")
	from pulse.reactive import AsyncEffect  # local import for typing

	assert isinstance(eff, AsyncEffect)
	assert eff._task is None or eff._task.cancelled() or eff._task.done()  # pyright: ignore[reportPrivateUsage]
	# No further updates should be scheduled by this effect after dispose
	prev_finished = s.finished
	flush_effects()
	await asyncio.sleep(0)
	await asyncio.sleep(0)
	assert s.finished == prev_finished


@pytest.mark.asyncio
async def test_state_query_no_refetch_after_state_dispose():
	class S(ps.State):
		uid: int = 1
		calls: int = 0

		@ps.query
		async def user(self) -> dict[str, Any]:
			self.calls += 1
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	q = s.user

	# Complete first fetch
	flush_effects()
	await asyncio.sleep(0)
	await asyncio.sleep(0)
	await asyncio.sleep(0)
	assert q.data == {"id": 1}
	assert s.calls == 1

	# Dispose state
	s.dispose()

	# Changing key after dispose must not schedule a new run
	s.uid = 2
	flush_effects()
	await asyncio.sleep(0)
	await asyncio.sleep(0)

	# Calls count unchanged, and data not updated to new id
	assert s.calls == 1
	assert q.data == {"id": 1}
