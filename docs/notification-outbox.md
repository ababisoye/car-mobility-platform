# Notification outbox integrity

Notification records start in `PENDING` and can move once to `PROCESSED` or `DISMISSED`. The conditional DynamoDB update requires the record to remain pending at write time, so two operators cannot overwrite each other's decision.

A missing notification returns HTTP 404. A repeated or competing finalization returns HTTP 409 and preserves the first terminal status. The demo records the shared staff role that processed the item; production must replace this with an individual managed identity.

This control uses the existing notification table and adds no AWS service or standing cost.
