# Existing Code Review

## Scope limitation
The official starter application's source was not available in the materials visible in the email screenshot. This file is a review checklist, not a claim that specific defects were found in unseen source code. Replace or supplement it with concrete file-and-line findings after inspecting the supplied starter app.

## Review checklist
1. Verify punch-in cannot be duplicated and punch-out cannot occur without an active punch-in.
2. Back application-level existence checks with database uniqueness and atomic updates.
3. Verify timezone-aware timestamps, overnight shifts, and work-date boundaries.
4. Reject blank employee IDs, invalid timestamps, negative durations, and malformed corrections.
5. Ensure every correction captures actor, timestamp, reason, and before/after values.
6. Run analytics in MongoDB and confirm treatment of incomplete shifts.
7. Return predictable HTTP errors without leaking stack traces or connection strings.
8. Add indexes for employee/date lookups, audit lookups, and uniqueness constraints.
9. Test duplicate punch-in, missing punch-in, duplicate punch-out, reversed timestamps, correction audit, empty analytics, and invalid date ranges.
10. Protect correction routes with authentication and authorization.

## Known limitations
- Work dates currently use UTC; confirm whether local office timezone is required.
- Audit writes and attendance updates are not transactionally coupled.
- Authentication is not included because no auth contract was visible.
- Review the actual starter code and API contract before final submission.
