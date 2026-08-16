# Training pipeline — from a job that runs to a model that answers

Feature 005. A training job that runs on the compute cluster built in feature
004, reads its data through the credential-less data store, tracks parameters
and metrics with MLflow, and produces a model artifact that Phase 2 registers
and serves through a batch endpoint.

**Status**: under construction. This file is rewritten at the end of Phase 1
(task T031) with the observed values and the answer to the MLflow tracking
question, and again at the end of Phase 2 (task T054).

See [the feature specification](../../specs/005-training-job-batch-endpoint/spec.md).
