# Booking lifecycle and fleet release

Customers can cancel an unpaid booking with `PATCH /bookings/{booking_id}` and their private `x-booking-token`. Online cancellation is unavailable after a trip starts, after a terminal status, or after payment is confirmed. A paid customer is directed to operations because the eventual provider's refund rules must be applied deliberately.

When an assigned booking becomes `CANCELLED`, `DECLINED` or `COMPLETED`, one DynamoDB transaction:

1. changes the booking status using its current status as a concurrency condition;
2. changes the assigned vehicle from `RESERVED` to `AVAILABLE`;
3. changes the assigned chauffeur from `ASSIGNED` to `AVAILABLE`;
4. queues the customer-facing terminal-status notification.

If any condition has changed, the whole transaction fails and staff are asked to refresh. The booking keeps its vehicle and chauffeur identifiers for operational history, together with `resources_released_at`, while overlap checks ignore terminal bookings.

Terminal bookings cannot receive new assignments. Terminal changes without assigned fleet still update the booking and notification together. The notification outbox does not invoke a paid delivery provider.
