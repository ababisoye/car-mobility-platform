# Atomic payment state changes

Signed provider webhooks update four related records: the payment request, the immutable provider-event receipt, the booking payment state and its customer notification. The demo applies these writes in one DynamoDB transaction.

Either all four changes succeed or none of them do. The transaction also requires the payment status to remain unchanged since verification, so competing provider events cannot overwrite one another. A provider retry with an event ID already recorded is acknowledged as a duplicate without sending a second customer notification. If another condition cancels the transaction and no matching event exists, the API returns HTTP 409 so the provider can retry safely.

This closes the gap where a partial failure could previously mark a payment paid while leaving its booking quoted. It reuses the existing payments and bookings tables and adds no AWS service or standing cost.

Payment-request creation follows the same rule: the new request, booking link and customer notification succeed together. The booking condition permits only its accepted latest quote and rejects a concurrent pending request.
