"""Minimal min-interval rate limiter for the read-only adapter."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class RateLimiter:
    min_interval_s: float = 0.5
    _last: float = field(default=0.0)

    def wait(self, now: float | None = None) -> float:
        """Return seconds to sleep to respect the min interval; updates last-call time.

        Pure/testable: pass ``now`` to avoid wall-clock dependence.
        """
        t = time.monotonic() if now is None else now
        delay = max(0.0, self.min_interval_s - (t - self._last))
        self._last = t + delay
        return delay
