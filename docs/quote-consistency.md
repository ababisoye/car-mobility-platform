# Atomic quotation workflows

Issuing a quote writes the immutable quote revision, updates the booking's latest-quote fields and queues the customer notification in one DynamoDB transaction. The booking must still be in the status reviewed by the operator, so concurrent revisions cannot silently overwrite one another.

Accepting or declining a quote updates the booking and queues the staff notification together. The transaction requires the same latest issued quote observed by the customer. A duplicate or stale decision returns HTTP 409 and creates no partial record.

These controls reuse the existing bookings, quotes and notifications tables. They add no AWS service or standing cost.
