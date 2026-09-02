# Fleet state controls

Administrators can manually move available, inactive and maintenance/off-duty resources between their appropriate operational states. `RESERVED`, `ON_TRIP` and `ASSIGNED` are system-managed states tied to booking transactions and cannot be selected manually.

The update condition requires the stored status to remain the one the administrator viewed. A concurrent change returns HTTP 409 instead of overwriting an assignment or trip transition. Assigned resources expose no manual next states until their booking transaction releases them.

These controls use conditional writes in the existing fleet tables and add no AWS service or standing cost.
