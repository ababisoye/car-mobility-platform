# Time-stable validation tests

Production date validation reads the real current time through a small clock boundary. The unit suite replaces that boundary with `2026-09-02T12:00:00` for each test and restores it afterward.

Booking-window, expiry and lifecycle fixtures therefore retain their intended meaning regardless of the calendar date on a developer machine or GitHub runner. This prevents an unchanged build from failing months later merely because fixed test dates became historical. Production Lambda behavior is unchanged.
