import time

t0 = time.perf_counter()
import pulse as ps  # pyright: ignore[reportUnusedImport]  # noqa: E402, F401, I001

t1 = time.perf_counter()

print(f"importing Pulse took {t1 - t0}s")
