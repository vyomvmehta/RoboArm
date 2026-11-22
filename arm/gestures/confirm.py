"""Hold-to-confirm (V2-2): a command gesture only counts after it has been held steadily.

Why: classifying single frames flickers (a hand passing through a fist shape on its way to
something else would send the arm home). So a label must make up at least `min_visible_fraction`
of the frames over the last `hold_s` seconds before it fires, and it fires ONCE.

Re-arming: the same gesture fires again only after it has been completely absent for `hold_s`.
A single dropped or misread frame in the middle of a held fist must NOT fire "home" twice (or,
worse, "replay" twice).
"""
from __future__ import annotations

from collections import deque


class Confirmer:
    def __init__(self, hold_s: float = 0.5, min_visible_fraction: float = 0.8):
        self.hold_s = hold_s
        self.min_frac = min_visible_fraction
        self._window: deque[tuple[float, str | None]] = deque()
        self._fired: str | None = None          # last label that fired, until it has gone away

    def update(self, label: str | None, t: float) -> str | None:
        """label = classify() result, or None when no hand is visible.

        Returns the label once, on the frame it is confirmed; None otherwise.
        """
        self._window.append((t, label))
        while self._window and t - self._window[0][0] > self.hold_s:
            self._window.popleft()

        if self._fired is not None and all(l != self._fired for _, l in self._window):
            self._fired = None                   # gone for a full hold time: re-armed

        if label in (None, "none") or label == self._fired:
            return None
        span = t - self._window[0][0]
        share = sum(1 for _, l in self._window if l == label) / len(self._window)
        if span >= self.hold_s * 0.95 and share >= self.min_frac:
            self._fired = label
            return label
        return None

    def reset(self) -> None:
        self._window.clear()
        self._fired = None
