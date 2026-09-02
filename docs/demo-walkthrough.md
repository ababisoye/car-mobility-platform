# Five-minute portfolio walkthrough

This walkthrough demonstrates the business workflow and cloud-engineering decisions locally. It requires no AWS account, creates no cloud resources and uses only in-memory synthetic data.

## Start the demonstration

From the repository root:

```powershell
python scripts/preview-demo.py
```

Open `http://127.0.0.1:8080` for the customer view and `http://127.0.0.1:8080/admin` for operations. Use the preview-only administrator password printed by the script. Stopping the process deletes every local record.

## Demonstrate the customer journey

1. Select Lagos as the fleet hub and Interstate as the trip type.
2. Choose a destination state outside Lagos. Notice that Lagos is disabled in the state selector.
3. Enter synthetic contact details, pickup and destination text, and future pickup/end times.
4. Submit the request and save the booking reference and one-time access token shown on screen.
5. Use **Check my booking** with both values. Explain that the booking ID identifies a record while the separate high-entropy token authorizes the limited customer view.

Point out that the browser creates an idempotency key before submission. A safe retry returns the original booking instead of creating a duplicate booking or notification.

## Demonstrate operations

1. Open the operations dashboard and sign in as the preview administrator.
2. Add an available vehicle in the Lagos hub.
3. Add a Lagos chauffeur and mark **Interstate approved** as Yes.
4. Move the booking from `REQUESTED` to `REVIEWING`.
5. Issue a quote with an amount and a future expiry.
6. Return to the customer view, check the booking again and accept the quote.
7. Return to operations, refresh, move the booking to `CONFIRMED`, and assign the vehicle and approved chauffeur.
8. Move the booking to `IN_PROGRESS`, then `COMPLETED`. Confirm the vehicle and chauffeur become available again.

For a useful negative demonstration, create another chauffeur without interstate approval and try assigning that person to the interstate booking. The API rejects the assignment before any database transaction.

## Explain the engineering decisions

- The zero-funding design uses one constrained Python Lambda, a Function URL and six minimum-capacity DynamoDB tables; it deliberately omits NAT Gateway, load balancers, API Gateway, containers and RDS.
- DynamoDB transactions keep booking, quote, fleet and notification changes atomic. Conditional expressions reject stale or conflicting updates.
- Customer tokens are stored only as SHA-256 hashes. Staff credentials use salted PBKDF2 hashes, and payment-provider events use a separate HMAC boundary.
- GitHub Actions runs the complete automated test suite, Terraform formatting and validation for every repository change. CI actions are pinned to immutable commits with read-only default permissions.
- The local preview emulates the transactional lifecycle and is smoke-tested from booking creation through trip completion.
- The production Terraform foundation is intentionally separate. It demonstrates multi-AZ networking, encrypted storage/database design, remote state and cost controls without pretending those paid resources are currently deployed.

## Be explicit about limitations

This is a portfolio demonstration, not a live rental service. It has no managed customer identity, individual workforce accounts, MFA, WAF, production rate limiting, real payment processing, identity-document handling or durable audit retention. The [architecture decisions](architecture-decisions.md) and [threat model](threat-model.md) explain the accepted demo risks and production promotion requirements.

## Stop and reset

Press `Ctrl+C` in the terminal running the preview. Restarting the script creates a clean in-memory environment. No cleanup in AWS is necessary because the walkthrough never contacts AWS.
