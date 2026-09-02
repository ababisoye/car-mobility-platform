# Customer booking access

Booking references identify records; they are not treated as secrets. When a booking is created, the API also returns a separate high-entropy `access_token` exactly once.

The application stores only the token's SHA-256 hash. It does not store the plaintext token, include it in staff booking responses, or write it to structured logs. Customer status endpoints compare hashes with a timing-safe function.

## Customer requests

Send the token in `x-booking-token` when requesting:

- `GET /bookings/{booking_id}`
- `GET /bookings/{booking_id}/quote`
- `GET /bookings/{booking_id}/payment`

Missing and incorrect credentials both receive the same `404` response. This avoids confirming whether a submitted booking reference exists.

The booking page displays the reference and access token after submission. The customer must save both. The zero-funding demo intentionally has no email/SMS recovery channel because that would require a delivery provider.

The same page provides a **Check my booking** form. It sends both values in request headers, never in the URL, and displays the booking workflow status plus the latest quote and payment state when available. The token input uses password masking and is not written to browser storage.

## Handling rules

- Never place the token in a URL, query string, analytics event or log message.
- Never send it to staff through public chat or issue trackers.
- Use HTTPS outside localhost.
- Treat possession of both values as authority to read the limited customer view.
- Rotate or replace this mechanism with authenticated customer accounts before storing identity documents or enabling sensitive actions.

This token protects read access; it does not authenticate payments, staff actions or provider webhooks, which use separate credentials.
