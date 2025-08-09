import asyncio
import pytest

import pulse as ps
from pulse.reactive import flush_effects


async def run_query():
    print('--- Running query ----')
    flush_effects()  # runs the effect
    await asyncio.sleep(0)  # runs the _do_fetch async function
    await asyncio.sleep(0)  # runs the actual async query
    await asyncio.sleep(0)
    print('--- Query should be finished ----')


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
        async def user(self):  
            ...

    with pytest.raises(RuntimeError, match="missing a '@user.key'"):
        Bad()
