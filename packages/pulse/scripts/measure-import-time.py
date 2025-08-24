import time

t0 = time.perf_counter()
import pulse as ps

t1 = time.perf_counter()

print(f"importing Pulse took {t1 - t0}s")
