# Employee Attendance & Analytics API

FastAPI + MongoDB backend for employee punch-in/out, manual corrections with audit history, and attendance analytics using MongoDB aggregation pipelines.

## Requirements
- Python 3.11+
- Git
- MongoDB 6.0+ (local instance or MongoDB Atlas)

## Setup (Windows PowerShell)
```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:MONGODB_URI = "mongodb://localhost:27017"
$env:DATABASE_NAME = "hrone_attendance"
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000/docs and check http://127.0.0.1:8000/health.

## Endpoints
| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | API and MongoDB health |
| POST | `/attendance/punch-in` | Start daily attendance |
| POST | `/attendance/punch-out` | End active attendance |
| GET | `/attendance` | Filter and paginate records |
| PATCH | `/attendance/{record_id}/correction` | Correct attendance with actor and reason |
| GET | `/attendance/{record_id}/audit` | View audit history |
| GET | `/analytics/summary?start_date=2026-10-01&end_date=2026-10-31` | Date-range summary |
| GET | `/analytics/employee/{employee_id}` | Employee-level analytics |

## Example request bodies
Punch in/out:
```json
{"employee_id":"EMP-001"}
```
Correction:
```json
{"corrected_by":"hr-admin","reason":"Approved correction based on signed register","punch_in":"2026-10-14T09:00:00Z"}
```

## Business rules
- One record per employee per UTC calendar date, enforced by a unique compound index.
- Duplicate punch-ins and repeated punch-outs are rejected.
- Punch-out requires a same-day punch-in and cannot precede punch-in.
- Manual corrections require an actor and reason and record before/after values in a separate audit collection.
- Summary and employee analytics run MongoDB aggregation pipelines.
- Naive timestamps are treated as UTC; aware timestamps are normalized to UTC.

## Collections
`attendance`: employee_id, work_date, punch_in, punch_out, status, total_minutes, created_at, updated_at, audit_version.

`attendance_audit`: event_id, attendance_id, employee_id, action, changed_at, changed_by, reason, before, after.

Read [DECISIONS.md](DECISIONS.md) and [REVIEW.md](REVIEW.md).

## Assignment compatibility note
The starter kit and its exact OpenAPI contract were not accessible from the email screenshot. Before submitting, compare endpoint names, data fields, sample data, and response shapes against the official kit and update any differences. The review document explicitly distinguishes a review checklist from inspection of unseen source code.

## Basic tests
Run `pytest` after installing dependencies. Tests currently cover timestamp normalization and UTC date-key behavior.
