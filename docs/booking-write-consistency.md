# Atomic booking creation

The initial booking record and its `BOOKING_REQUESTED` notification are written in one DynamoDB transaction. Either both records exist or neither does.

This transaction works with duplicate-safe browser submissions. If the transaction succeeded but the HTTP response was lost, the browser retries with the same idempotency key and customer token and receives the original booking without creating a second notification. If the transaction fails, no booking or notification remains.

The control reuses the existing bookings and notifications tables and adds no AWS service or standing cost.
