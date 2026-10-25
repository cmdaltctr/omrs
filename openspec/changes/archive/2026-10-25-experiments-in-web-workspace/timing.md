# Timing: scan and check on each request (task 2.1)

Design D4 needs `scan` plus `check` of the repository `experiments/` folder to take under 200 ms.

## Result

| Measure | Value |
|---|---|
| Folders detected | 50 |
| Findings | 48 (0 errors, 4 warnings, 44 info) |
| Median (20 warm repetitions) | 6.3 ms |
| Maximum | 8.2 ms |
| Minimum | 5.5 ms |

The median is far below 200 ms. D4 stays as written: no cache file.

## Method

- Machine: the developer machine (Apple silicon, arm64, macOS 27), Python 3.14.7.
- Commit: `7c998637` on `feat/experiments-in-web-workspace`.
- One warm-up call, then 20 timed repetitions of `scan_experiments(root)` followed by `check_experiments(root)`. `check_experiments` scans again inside, so each repetition holds two scans. The route does the same work.
- The script was a scratch file and is not committed. Command:

```bash
uv run --no-sync python <scratch>/time_scan.py experiments
```

Script body:

```python
import statistics, sys, time
from pathlib import Path
from omrs.core.experiment_records.check import check_experiments
from omrs.core.experiment_records.scan import scan_experiments

root = Path(sys.argv[1])
scan_experiments(root)
check_experiments(root)  # warm-up
times = []
for _ in range(20):
    start = time.perf_counter()
    folders = scan_experiments(root)
    findings = check_experiments(root)
    times.append((time.perf_counter() - start) * 1000)
print(f"median_ms={statistics.median(times):.1f} max_ms={max(times):.1f}")
```
