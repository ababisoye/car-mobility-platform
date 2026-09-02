# Booking state machine

The API, not the dashboard, is the source of truth for booking transitions. Staff responses include `allowed_transitions`, and the dashboard uses that list to avoid presenting invalid actions.

```text
REQUESTED -> REVIEWING -> QUOTED -> CONFIRMED -> ASSIGNED -> IN_PROGRESS -> COMPLETED
     |           |          |           |            |
     +-----------+----------+-----------+------------+--> CANCELLED
     |           |          |
     +-----------+----------+----------------------------> DECLINED
                         |
                         +--> REVIEWING (quote declined or revision needed)
```

Operational guards supplement the transition graph:

- issuing a quote is limited to request, review and quoted stages;
- confirmation requires an accepted quote or a confirmed payment;
- fleet assignment requires a confirmed booking and uses a DynamoDB condition that checks that state again;
- payment requests require the latest accepted quote and a quoted booking;
- assignment is the only operation that enters `ASSIGNED`;
- completion requires an assigned trip that first entered `IN_PROGRESS`;
- terminal states have no outgoing transitions;
- pending or paid bookings cannot be cancelled until operations resolves the payment.

Payment webhooks remain the authoritative automated route from an accepted, quoted booking to `CONFIRMED`. The shared status-change function uses optimistic concurrency so simultaneous staff actions fail with a refresh instruction rather than overwriting each other.
