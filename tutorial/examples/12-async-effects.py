from pathlib import Path
import pulse as ps
import asyncio


class AsyncEffectState(ps.State):
    running: bool = False
    step: int = 0

    @ps.effect(lazy=True)
    async def ticker(self):
        # Simulate writes across awaits
        await asyncio.sleep(0.5)
        with ps.Untrack():
            self.step += 1
            self.step += 1
        await asyncio.sleep(0.5)
        # Keep going by rescheduling itself through a signal
        self.step += 1

    def start(self):
        # Manually schedule an effect
        self.ticker.schedule()
        self.running = True

    def stop(self):
        self.ticker.cancel()
        self.running = False


@ps.component
def AsyncEffectDemo():
    state = ps.states(AsyncEffectState)

    return ps.div(
        className="h-screen w-fit mx-auto flex flex-col justify-center items-start"
    )[
        ps.div(
            ps.button(
                "Start async effect",
                onClick=state.start,
                className="px-4 py-2 bg-gray-500 text-white rounded hover:bg-gray-600",
            ),
            ps.button(
                "Stop",
                onClick=state.stop,
                className="px-4 py-2 bg-gray-500 text-white rounded hover:bg-gray-600 ml-2",
            ),
            className="mb-2",
        ),
        ps.p(f"Running: {state.running}", className="text-sm"),
        ps.p(f"Step: {state.step}", className="text-sm"),
    ]


app = ps.App(
    routes=[ps.Route("/", AsyncEffectDemo)],
)
