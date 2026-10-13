"""How long a batch has left: worked out from how much of the whole batch is done after how long, so it stays
steady (it doesn't start over each time a new file begins, and paused time doesn't count)."""

from __future__ import annotations

MIN_WORK_S = 3.0  # say nothing until the batch has run this long…
MIN_DONE = 0.02  # …and this much of it is done
SMOOTH = 0.3  # how much a new reading moves the estimate (the rest is the old one, counted down)


class BatchClock:
    def __init__(self, now: float):
        self.t0 = now
        self.paused_s = 0.0
        self.pause_t0: float | None = None
        self.est: float | None = None  # seconds left, as of est_at
        self.est_at = now

    def pause(self, now: float) -> None:
        if self.pause_t0 is None:
            self.pause_t0 = now

    def resume(self, now: float) -> None:
        if self.pause_t0 is not None:
            self.paused_s += now - self.pause_t0
            if self.est is not None:
                self.est_at += now - self.pause_t0  # the estimate didn't count down while paused
            self.pause_t0 = None

    def worked(self, now: float) -> float:
        """Seconds spent converting (paused time left out)."""
        end = self.pause_t0 if self.pause_t0 is not None else now
        return max(0.0, end - self.t0 - self.paused_s)

    def _counted_down(self, now: float) -> float | None:
        if self.est is None:
            return None
        if self.pause_t0 is not None:
            now = self.pause_t0
        return max(0.0, self.est - (now - self.est_at))

    def left(self, done: float, total: float, now: float) -> float | None:
        """Seconds left, or None until there's enough to go on. `done` and `total` are in the same units
        (seconds of media, with a little for each photo)."""
        worked = self.worked(now)
        if total <= 0 or done <= 0 or worked < MIN_WORK_S or done / total < MIN_DONE:
            return self._counted_down(now)
        fresh = worked * max(0.0, total - done) / done
        before = self._counted_down(now)
        est = fresh if before is None else before * (1 - SMOOTH) + fresh * SMOOTH
        if self.pause_t0 is None:
            self.est, self.est_at = est, now
        return est


def time_left(sec: float) -> str:
    """Plain words, rounded so it doesn't flicker: "Less than a minute left", "About 4 min left"."""
    if sec < 45:
        return "Less than a minute left"
    if sec < 90:
        return "About a minute left"
    minutes = round(sec / 60)
    if minutes < 60:
        return f"About {minutes} min left"
    h, m = divmod(minutes, 60)
    return f"About {h} hr {m} min left" if m else f"About {h} hr left"
