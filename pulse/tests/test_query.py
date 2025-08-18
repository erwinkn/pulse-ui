import asyncio
import pytest

import pulse as ps
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
        async def user(self) -> dict:
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
        async def user(self) -> dict:
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

    # First fetch (scheduled on property access)
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


def test_state_query_missing_key_raises():
    class Bad(ps.State):
        @ps.query
        async def user(self): ...

    with pytest.raises(RuntimeError, match="missing a '@user.key'"):
        Bad()


@pytest.mark.asyncio
async def test_state_query_keep_previous_data_on_refetch_default():
    class S(ps.State):
        uid: int = 1

        @ps.query
        async def user(self) -> dict:
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
        async def user(self) -> dict:
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
        async def user(self) -> dict:
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
        async def user(self) -> dict:
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
        async def user(self) -> dict:
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
