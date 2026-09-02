# Quote profitability

Staff may include `estimated_cost_ngn` when issuing a quote through
`POST /admin/bookings/{booking_id}/quotes`. The platform calculates and stores:

- `estimated_margin_ngn`: selling price minus estimated cost;
- `estimated_margin_bps`: estimated margin as basis points of the selling price;
- `cost_status`: `ESTIMATED` when a cost was supplied, otherwise `NOT_ESTIMATED`.

The estimate is optional because operations may not know every supplier, fuel,
toll, accommodation or positioning cost when a quote is first prepared. A
missing estimate is represented explicitly and is never treated as zero cost.
Negative margins are retained rather than rejected so staff can identify a
loss-making quote.

These fields are internal. They appear in the authenticated staff quote history
but are deliberately excluded from the customer quote endpoint. This is an
estimate for quoting decisions, not accounting profit; actual costs and overhead
will require a later reconciliation workflow.
