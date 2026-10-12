# Testing Standards

## Unit Tests

Unit tests must not touch the network or the filesystem. Any dependency crossing a process boundary is replaced with a fake so that the suite remains deterministic. The full unit suite is expected to complete in under two minutes on typical developer hardware, because a slow suite stops being run locally and starts being discovered only in the pipeline.

## Integration Tests

Integration tests run against ephemeral containers started by the test harness and torn down afterwards. They cover the interaction between a service and its own datastore, and the contract with any upstream dependency. They deliberately do not attempt to cover business logic already covered by unit tests, since duplicating that coverage slows the pipeline without improving confidence.

## Flaky Tests

A test that fails intermittently is quarantined within one business day and either fixed or deleted within one week. Quarantined tests do not block the pipeline but appear in a weekly report to the owning team. Tolerating a flaky test is treated as a correctness problem rather than an inconvenience, because engineers quickly learn to rerun failures rather than investigate them.
