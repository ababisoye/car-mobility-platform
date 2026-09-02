# Operational reporting

`GET /admin/summary` provides staff-only operational aggregates using the existing booking, vehicle, chauffeur and payment tables. Both administrator and operator roles can read it.

The response includes:

- bookings by workflow status and hub;
- interstate and accepted-quote counts;
- vehicles and chauffeurs by availability status;
- payment counts plus paid and pending NGN totals.

No customer name, contact detail, trip address, note, credential or booking token is returned. The dashboard renders four headline cards from these aggregates.

## Demonstration boundary

Each table read is deliberately capped at 100 records and the response labels that scope as `bounded_demo_scan`. This keeps implementation and infrastructure small, but totals become incomplete beyond that bound. A funded production design should use paginated queries, event-driven counters or a dedicated analytics store after retention, reconciliation and reporting requirements are agreed.
