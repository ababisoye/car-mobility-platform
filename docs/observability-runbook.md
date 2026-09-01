# Observability and incident runbook

The demo writes one-line JSON records to standard output. Lambda sends those records to the existing CloudWatch log group, which retains them for one day in zero-funding mode. No custom metrics, tracing service or paid monitoring vendor is enabled.

## Log contract

Every request produces `request_started` and `request_completed` records. Unhandled failures produce `request_failed`. Each record includes:

- `timestamp`, `level`, `service` and `release_version`
- `request_id`, also returned to the caller as `x-request-id`
- HTTP method, path, status and duration where applicable
- non-sensitive workflow identifiers on booking, quote, assignment and payment events

Request bodies, headers, customer names, phone numbers, email addresses, notes, passwords, signatures and webhook secrets must never be logged.

## Health check

Request `GET /health`. A healthy response reports the service name, current Lambda release version and `zero-funding-demo` mode. The release version can be compared with the version recorded by the deployment workflow.

## CloudWatch Logs Insights queries

Use the narrowest useful time range because Logs Insights charges by data scanned outside applicable free allowances.

Recent failures:

```text
fields @timestamp, level, event, request_id, method, path, status_code, error_type
| filter level = "ERROR"
| sort @timestamp desc
| limit 50
```

Follow one request from the `x-request-id` response header:

```text
fields @timestamp, event, level, method, path, status_code, duration_ms
| filter request_id = "REPLACE_WITH_REQUEST_ID"
| sort @timestamp asc
```

Request volume and latency:

```text
filter event = "request_completed"
| stats count(*) as requests, pct(duration_ms, 95) as p95_ms by bin(5m)
```

Payment outcomes:

```text
fields @timestamp, request_id, booking_id, payment_id, provider_event_id, payment_status
| filter event = "payment_webhook_applied"
| sort @timestamp desc
```

## Incident sequence

1. Record the failing request's `x-request-id`, approximate time and visible symptom without copying customer data.
2. Check `/health` and note `release_version`.
3. Search the request ID, then inspect nearby `ERROR` events.
4. Compare the first failures with the latest deployment time and Lambda version.
5. If the release caused the incident, follow the rollback procedure in `release-runbook.md`.
6. Repeat the health and booking smoke tests after rollback.
7. Document the cause and corrective test before promoting a replacement version.

Do not extend log retention or enable paid telemetry until its expected monthly cost and data-handling policy are approved.
