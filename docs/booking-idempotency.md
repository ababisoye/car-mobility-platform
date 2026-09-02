# Duplicate-safe booking submission

The browser creates a random idempotency key and customer token before submitting a booking. If a network timeout leaves the outcome unclear, it retries with both values and the same request body.

The API derives a stable booking identifier from the SHA-256 hash of the idempotency key, stores only the hash of the customer token, and fingerprints the validated booking fields. An identical retry returns the original booking with HTTP 200 and does not create another notification. Reusing the key with different booking details or a different token returns HTTP 409.

Clients that omit both headers retain the original one-shot HTTP 201 behaviour. Idempotency values must not contain customer data and should be treated as short-lived credentials. This control uses the existing bookings table and creates no additional AWS service or standing cost.
