# API hardening

The zero-funding demo rejects malformed traffic at the application boundary:

- Request bodies are limited to 16 KB before JSON parsing.
- Resource routes match their exact documented shape; extra path segments are rejected.
- Booking, vehicle, chauffeur and notification identifiers must be canonical UUIDs.
- Booking phone and optional email fields receive basic format validation.
- Pickup must be in the future and no more than 366 days away; a request may span at most 30 days.
- Interstate requests require a recognized Nigerian destination state different from the selected fleet hub state; local requests cannot name a different destination state.

These controls reduce accidental and low-effort abuse, but they are not a production edge-security layer. The deliberately small Lambda concurrency and DynamoDB capacity settings limit cost exposure; they do not replace rate limiting. Before a public production launch, approve a budget and add managed throttling, bot protection and monitoring at the edge.
