# Design Decisions

## FastAPI and PyMongo
Synchronous PyMongo is paired with ordinary `def` endpoints so database calls do not block the async event loop. The service can migrate to an async driver if required.

## One record per employee per work date
A unique compound index on `employee_id + work_date` is the final concurrency guard. Application checks provide readable errors; the index prevents concurrent duplicate inserts.

## UTC normalization
Naive timestamps are interpreted as UTC and aware timestamps are converted to UTC. Confirm whether the official contract expects office-local dates; if so, calculate `work_date` using an explicit configured timezone.

## Separate audit collection
Audit events capture actor, reason, timestamp, and before/after values. In production, attendance updates and audit inserts should be in a MongoDB transaction when supported, so one cannot succeed without the other.

## Derived duration
Worked minutes are calculated from punch-in/out and recalculated after time corrections. Timestamps remain the source of truth.

## MongoDB aggregation
Analytics use `$match`, `$group`, `$addToSet`, and `$project` in MongoDB instead of loading records into application memory.

## HTTP semantics
- 201: new punch-in
- 404: attendance record not found
- 409: duplicate or conflicting state transition
- 422: invalid date order or correction payload

## Authentication
No authentication contract was visible in the assignment email screenshot. The correction endpoint records `corrected_by`, but production code must derive actor identity from authenticated credentials rather than trusting client input.
