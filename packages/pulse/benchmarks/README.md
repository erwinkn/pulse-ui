# Serializer benchmarks

Run both warmed serializer suites:

```bash
make benchmark-serializer
```

Each fixture measures a full serialize/deserialize round trip. Samples last at
least 100 ms, report the median of seven samples, and rerun up to twice when the
coefficient of variation exceeds 5%.

The fixtures cover a small callback, a roughly 71 KB VDOM payload, 800 records
with temporal/Set/NaN values, and 3,000 references to one shared record.

The one-time v4 comparison was run in-process before its implementation was
removed. Results are recorded here so v4 does not remain in production solely
for benchmarking.

| Runtime | Fixture | v5/v4 time | v5/v4 wire size |
|---|---|---:|---:|
| JavaScript | Small callback | 0.95x | 0.86x |
| JavaScript | VDOM | 1.15x | 1.00x |
| JavaScript | Mixed special | 1.93x | 1.13x |
| JavaScript | 3,000 references | 0.60x | 1.21x |
| Python | Small callback | 1.06x | 0.86x |
| Python | VDOM | 1.02x | 1.00x |
| Python | Mixed special | 1.71x | 1.13x |
| Python | 3,000 references | 1.70x | 1.21x |
