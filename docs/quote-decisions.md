# Customer quote decisions

Customers can accept or decline the latest quote from the status panel or through `PATCH /bookings/{booking_id}/quote`. The request requires the private `x-booking-token` issued when the booking was created.

The decision endpoint accepts only `ACCEPTED` or `DECLINED`. It rejects expired quotes, superseded quote versions, repeated decisions and invalid customer credentials. A conditional DynamoDB update prevents a decision from being attached to a quote that changed concurrently.

An accepted quote remains in the `QUOTED` booking stage and unlocks creation of its matching payment request. A declined quote returns the booking to `REVIEWING` so staff can prepare a revision. Issuing any new quote resets the decision, ensuring an earlier acceptance cannot authorize payment against a later price.

Each decision queues a staff-facing event in the provider-neutral notification outbox. Zero-funding mode stores that event without sending paid email, SMS or WhatsApp messages.
