"""When Blue Jay's test API may be called, in Vietnam time.

Blue Jay restricts the testing API to a few short windows each day. Calling
outside them fails even with correct credentials, so "may I call?" has to be a
first-class question the app can answer rather than something a developer
remembers.

Two of the three documented windows are unambiguous. The third is written
``24:00-24:59``, which is not clock notation. It is carried here so the
ambiguity stays visible, and it is marked UNCONFIRMED so that no automated
call is ever made on the strength of a guess about what it means.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

#: Every window is expressed in this zone; the document states Vietnam time.
VIETNAM = ZoneInfo("Asia/Ho_Chi_Minh")


@dataclass(frozen=True)
class TestingWindow:
    start: time
    #: The last minute INSIDE the window; 16:59 means 16:59:59 is still in.
    #:
    #: The two documented strings use different notations. ``16:00-16:59``
    #: names the last included minute — through-end-of-minute gives a natural
    #: 60 minutes. ``08:00-08:30`` names the END INSTANT — reading it the same
    #: way would give a 31-minute window, which nothing would specify. So each
    #: is read at its NARROWER interpretation and the morning window ends at
    #: 08:29. The asymmetry is deliberate: being a minute short never causes a
    #: rejected call, being a minute long does.
    end: time
    confirmed: bool
    source_text: str
    note: str = ""


TESTING_WINDOWS: tuple[TestingWindow, ...] = (
    TestingWindow(time(8, 0), time(8, 29), True, "08:00-08:30"),
    TestingWindow(time(16, 0), time(16, 59), True, "16:00-16:59"),
    TestingWindow(
        time(0, 0),
        time(0, 59),
        False,
        "24:00-24:59",
        note=(
            "The source document writes '24:00-24:59', which is not standard clock "
            "notation. 00:00-00:59 of the following day is the likely reading, but it "
            "is UNCONFIRMED, so this window never reports as open. Confirm with Blue Jay."
        ),
    ),
)


@dataclass(frozen=True)
class WindowStatus:
    now_vn: datetime
    is_open: bool
    window: TestingWindow | None
    next_open_at: datetime | None
    seconds_until_open: int
    unconfirmed_note: str | None


def _within(moment: datetime, window: TestingWindow) -> bool:
    # Compare to the minute so the END minute counts in full: at second
    # granularity 16:59:30 would otherwise fall outside `end == 16:59:00`.
    return (
        (window.start.hour, window.start.minute)
        <= (moment.hour, moment.minute)
        <= (window.end.hour, window.end.minute)
    )


def confirmed_windows() -> tuple[TestingWindow, ...]:
    return tuple(w for w in TESTING_WINDOWS if w.confirmed)


def window_status(now: datetime | None = None) -> WindowStatus:
    """Whether the testing API may be called right now.

    A naive datetime RAISES. Assuming a zone is precisely how a call gets made
    seven hours outside the window.
    """
    if now is None:
        now = datetime.now(tz=VIETNAM)
    if now.tzinfo is None or now.tzinfo.utcoffset(now) is None:
        raise ValueError(
            "window_status needs a timezone-aware datetime — Blue Jay's windows are "
            "in Asia/Ho_Chi_Minh and a naive value would be judged in the wrong zone."
        )

    local = now.astimezone(VIETNAM)
    open_window = next((w for w in confirmed_windows() if _within(local, w)), None)

    upcoming = [
        datetime.combine(local.date() + timedelta(days=offset), w.start, tzinfo=VIETNAM)
        for w in confirmed_windows()
        for offset in (0, 1)
    ]
    future = sorted(dt for dt in upcoming if dt > local)
    next_open_at = future[0] if future else None

    unconfirmed = next((w for w in TESTING_WINDOWS if not w.confirmed and _within(local, w)), None)

    return WindowStatus(
        now_vn=local,
        is_open=open_window is not None,
        window=open_window,
        next_open_at=next_open_at,
        seconds_until_open=(
            0 if open_window else int((next_open_at - local).total_seconds()) if next_open_at else 0
        ),
        unconfirmed_note=unconfirmed.note if unconfirmed else None,
    )


def may_call(now: datetime | None = None) -> bool:
    """The single predicate every outbound call must pass."""
    return window_status(now).is_open
