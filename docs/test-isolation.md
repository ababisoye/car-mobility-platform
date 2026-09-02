# Isolated application tests

Each application test starts with empty in-memory bookings, fleet, quotes, notifications and payment tables. Tests therefore cannot pass because a previous test happened to create a required record, and changing test order does not change the starting database state.

The suite also restores patched logging and clock functions after each test. These boundaries keep local and GitHub CI results reproducible without creating AWS resources.
