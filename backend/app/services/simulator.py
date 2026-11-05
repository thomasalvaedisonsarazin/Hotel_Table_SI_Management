"""Fake camera observations for demo restaurants. Never runs against a real restaurant."""

import random
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class TableScript:
    """Plays out arrive, get served, leave, get cleaned on a loop for one table."""

    rng: random.Random
    seats: int
    next_arrival: datetime
    phase: str = "empty"
    party_size: int = 0
    staff_from: datetime | None = None
    staff_until: datetime | None = None
    leave_at: datetime | None = None
    clean_from: datetime | None = None
    clean_until: datetime | None = None

    def _plan_visit(self, now: datetime) -> None:
        self.party_size = self.rng.randint(1, self.seats)
        # About 3 in 10 parties wait long enough to trigger the demo's 45 second waiter alert.
        delay = self.rng.uniform(55, 80) if self.rng.random() < 0.3 else self.rng.uniform(8, 30)
        self.staff_from = now + timedelta(seconds=delay)
        self.staff_until = self.staff_from + timedelta(seconds=6)
        self.leave_at = self.staff_until + timedelta(seconds=self.rng.uniform(40, 110))

    def _plan_cleaning(self, now: datetime) -> None:
        self.clean_from = now + timedelta(seconds=self.rng.uniform(10, 40))
        self.clean_until = self.clean_from + timedelta(seconds=8)

    def observe(self, now: datetime) -> tuple[int, bool]:
        """Return (guest_count, staff_present) as a camera would report them at this moment."""
        if self.phase == "empty":
            if now < self.next_arrival:
                return 0, False
            self._plan_visit(now)
            self.phase = "seated"
        if self.phase == "seated":
            assert self.leave_at and self.staff_from and self.staff_until  # noqa: S101
            if now < self.leave_at:
                return self.party_size, self.staff_from <= now < self.staff_until
            self._plan_cleaning(now)
            self.phase = "dirty"
        assert self.clean_from and self.clean_until  # noqa: S101
        if now < self.clean_until:
            return 0, self.clean_from <= now
        self.next_arrival = now + timedelta(seconds=self.rng.uniform(10, 45))
        self.phase = "empty"
        return 0, False
