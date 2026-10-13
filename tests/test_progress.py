"""The time left on a batch stays steady: it doesn't reset when a new file starts or count paused time."""

from __future__ import annotations

from listo.core.progress import BatchClock, time_left


def test_nothing_until_there_is_enough_to_go_on():
    c = BatchClock(0.0)
    assert c.left(0.0, 100.0, 1.0) is None
    assert c.left(1.0, 100.0, 2.0) is None  # too early


def test_the_estimate_follows_the_whole_batch_and_never_drops_back_to_unknown():
    c = BatchClock(0.0)
    first = c.left(10.0, 100.0, 10.0)  # 10% in 10 s: about 90 s left
    assert first is not None and abs(first - 90.0) < 1e-6
    # a new file starts and nothing new is done for a moment: still an answer, counting down
    assert c.left(10.0, 100.0, 12.0) is not None
    later = c.left(50.0, 100.0, 50.0)
    assert later is not None and 30.0 < later < 70.0


def test_paused_time_does_not_count():
    c = BatchClock(0.0)
    c.left(10.0, 100.0, 10.0)
    c.pause(10.0)
    assert c.worked(500.0) == 10.0
    held = c.left(10.0, 100.0, 500.0)
    assert held is not None and abs(held - 90.0) < 1e-6  # frozen while paused
    c.resume(500.0)
    assert c.worked(510.0) == 20.0


def test_time_left_in_plain_words():
    assert time_left(20) == "Less than a minute left"
    assert time_left(70) == "About a minute left"
    assert time_left(4 * 60 + 10) == "About 4 min left"
    assert time_left(3600 + 5 * 60) == "About 1 hr 5 min left"
    assert time_left(2 * 3600) == "About 2 hr left"
