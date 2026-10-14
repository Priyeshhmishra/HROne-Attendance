"""Employee Attendance & Analytics API."""
from datetime import datetime, timezone, date
from typing import Any, Optional
from uuid import uuid4
import os

from bson import ObjectId
from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field, ConfigDict
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError, PyMongoError

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "hrone_attendance")
client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=2500, tz_aware=True)
db = client[DATABASE_NAME]
attendance = db["attendance"]
audit = db["attendance_audit"]

app = FastAPI(title="Employee Attendance & Analytics API", version="1.0.0",
              description="Punch-in/out, auditable corrections, and MongoDB analytics.")


@app.on_event("startup")
def ensure_indexes() -> None:
    attendance.create_index([("employee_id", ASCENDING), ("work_date", ASCENDING)], unique=True)
    attendance.create_index([("employee_id", ASCENDING), ("punch_in", DESCENDING)])
    attendance.create_index([("work_date", ASCENDING)])
    audit.create_index([("attendance_id", ASCENDING), ("changed_at", DESCENDING)])


class PunchRequest(BaseModel):
    employee_id: str = Field(min_length=1, max_length=100)
    at: Optional[datetime] = None


class CorrectionRequest(BaseModel):
    corrected_by: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=3, max_length=1000)
    punch_in: Optional[datetime] = None
    punch_out: Optional[datetime] = None
    status: Optional[str] = Field(default=None, pattern="^(present|absent|half_day|leave)$")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_dt(value: Optional[datetime]) -> datetime:
    dt = value or utc_now()
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def day_key(dt: datetime) -> str:
    return dt.date().isoformat()


def serialize(doc: dict[str, Any]) -> dict[str, Any]:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return doc


def get_record(record_id: str) -> dict[str, Any]:
    try:
        doc = attendance.find_one({"_id": ObjectId(record_id)})
    except Exception:
        doc = None
    if not doc:
        raise HTTPException(status_code=404, detail="Attendance record not found")
    return doc


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Employee Attendance & Analytics API", "docs": "/docs", "health": "/health"}


@app.get("/health")
def health() -> dict[str, str]:
    try:
        client.admin.command("ping")
        return {"status": "ok", "database": "connected"}
    except PyMongoError:
        raise HTTPException(status_code=503, detail="MongoDB is unavailable")


@app.post("/attendance/punch-in", status_code=status.HTTP_201_CREATED)
def punch_in(payload: PunchRequest) -> dict[str, Any]:
    employee_id = payload.employee_id.strip()
    if not employee_id:
        raise HTTPException(status_code=422, detail="employee_id cannot be blank")
    now = normalize_dt(payload.at)
    key = {"employee_id": employee_id, "work_date": day_key(now)}
    if attendance.find_one(key):
        raise HTTPException(status_code=409, detail="Attendance already exists for this employee and date")
    doc = {**key, "punch_in": now, "punch_out": None, "status": "present",
           "total_minutes": None, "created_at": utc_now(), "updated_at": utc_now(), "audit_version": 1}
    try:
        result = attendance.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Attendance already exists for this employee and date")
    doc["_id"] = result.inserted_id
    return serialize(doc)


@app.post("/attendance/punch-out")
def punch_out(payload: PunchRequest) -> dict[str, Any]:
    employee_id = payload.employee_id.strip()
    now = normalize_dt(payload.at)
    record = attendance.find_one({"employee_id": employee_id, "work_date": day_key(now)})
    if not record:
        raise HTTPException(status_code=404, detail="Punch-in record not found for this date")
    if record.get("punch_out") is not None:
        raise HTTPException(status_code=409, detail="Employee has already punched out")
    if now < record["punch_in"]:
        raise HTTPException(status_code=422, detail="Punch-out cannot be earlier than punch-in")
    minutes = int((now - record["punch_in"]).total_seconds() // 60)
    result = attendance.update_one(
        {"_id": record["_id"], "punch_out": None},
        {"$set": {"punch_out": now, "total_minutes": minutes, "updated_at": utc_now()},
         "$inc": {"audit_version": 1}},
    )
    if result.modified_count != 1:
        raise HTTPException(status_code=409, detail="Attendance was changed by another request; retry")
    updated = attendance.find_one({"_id": record["_id"]})
    audit.insert_one({"event_id": str(uuid4()), "attendance_id": str(record["_id"]),
        "employee_id": employee_id, "action": "punch_out", "changed_at": utc_now(),
        "changed_by": employee_id, "reason": "Employee punch-out",
        "before": {"punch_out": None}, "after": {"punch_out": now, "total_minutes": minutes}})
    return serialize(updated)


@app.get("/attendance")
def list_attendance(employee_id: Optional[str] = None, start_date: Optional[date] = None,
                    end_date: Optional[date] = None, limit: int = Query(100, ge=1, le=500),
                    skip: int = Query(0, ge=0)) -> dict[str, Any]:
    if start_date and end_date and end_date < start_date:
        raise HTTPException(status_code=422, detail="end_date must be on or after start_date")
    query: dict[str, Any] = {}
    if employee_id:
        query["employee_id"] = employee_id
    date_filter: dict[str, str] = {}
    if start_date:
        date_filter["$gte"] = start_date.isoformat()
    if end_date:
        date_filter["$lte"] = end_date.isoformat()
    if date_filter:
        query["work_date"] = date_filter
    total = attendance.count_documents(query)
    docs = attendance.find(query).sort([("work_date", DESCENDING), ("employee_id", ASCENDING)]).skip(skip).limit(limit)
    return {"items": [serialize(doc) for doc in docs], "total": total, "limit": limit, "skip": skip}


@app.patch("/attendance/{record_id}/correction")
def correct_attendance(record_id: str, payload: CorrectionRequest) -> dict[str, Any]:
    record = get_record(record_id)
    changes: dict[str, Any] = {}
    for field in ("punch_in", "punch_out", "status"):
        value = getattr(payload, field)
        if value is not None:
            changes[field] = normalize_dt(value) if field in ("punch_in", "punch_out") else value
    if not changes:
        raise HTTPException(status_code=422, detail="Provide at least one field to correct")
    next_in = changes.get("punch_in", record.get("punch_in"))
    next_out = changes.get("punch_out", record.get("punch_out"))
    if next_in and next_out and next_out < next_in:
        raise HTTPException(status_code=422, detail="Punch-out cannot be earlier than punch-in")
    if next_in and next_out:
        changes["total_minutes"] = int((next_out - next_in).total_seconds() // 60)
    elif "punch_in" in changes or "punch_out" in changes:
        changes["total_minutes"] = None
    before = {key: record.get(key) for key in changes}
    changes["updated_at"] = utc_now()
    changes["audit_version"] = int(record.get("audit_version", 1)) + 1
    attendance.update_one({"_id": record["_id"]}, {"$set": changes})
    audit.insert_one({"event_id": str(uuid4()), "attendance_id": str(record["_id"]),
        "employee_id": record["employee_id"], "action": "manual_correction", "changed_at": utc_now(),
        "changed_by": payload.corrected_by, "reason": payload.reason, "before": before,
        "after": {key: changes[key] for key in before}})
    return serialize(attendance.find_one({"_id": record["_id"]}))


@app.get("/attendance/{record_id}/audit")
def get_audit(record_id: str) -> dict[str, Any]:
    record = get_record(record_id)
    events = audit.find({"attendance_id": str(record["_id"])}).sort("changed_at", DESCENDING).limit(200)
    items = []
    for event in events:
        event["id"] = str(event.pop("_id"))
        items.append(event)
    return {"attendance_id": str(record["_id"]), "items": items}


@app.get("/analytics/summary")
def analytics_summary(start_date: date = Query(...), end_date: date = Query(...)) -> dict[str, Any]:
    if end_date < start_date:
        raise HTTPException(status_code=422, detail="end_date must be on or after start_date")
    pipeline = [
        {"$match": {"work_date": {"$gte": start_date.isoformat(), "$lte": end_date.isoformat()}}},
        {"$group": {"_id": None, "attendance_records": {"$sum": 1},
            "unique_employees": {"$addToSet": "$employee_id"},
            "present_records": {"$sum": {"$cond": [{"$eq": ["$status", "present"]}, 1, 0]}},
            "completed_shifts": {"$sum": {"$cond": [{"$ne": ["$punch_out", None]}, 1, 0]}},
            "total_minutes": {"$sum": {"$ifNull": ["$total_minutes", 0]}},
            "average_minutes": {"$avg": "$total_minutes"}}},
        {"$project": {"_id": 0, "attendance_records": 1,
            "unique_employees": {"$size": "$unique_employees"}, "present_records": 1,
            "completed_shifts": 1, "total_minutes": 1,
            "average_minutes": {"$round": [{"$ifNull": ["$average_minutes", 0]}, 2]}}},
    ]
    result = list(attendance.aggregate(pipeline))
    empty = {"attendance_records": 0, "unique_employees": 0, "present_records": 0,
             "completed_shifts": 0, "total_minutes": 0, "average_minutes": 0}
    return {"start_date": start_date.isoformat(), "end_date": end_date.isoformat(),
            "summary": result[0] if result else empty}


@app.get("/analytics/employee/{employee_id}")
def employee_analytics(employee_id: str, start_date: Optional[date] = None,
                       end_date: Optional[date] = None) -> dict[str, Any]:
    if start_date and end_date and end_date < start_date:
        raise HTTPException(status_code=422, detail="end_date must be on or after start_date")
    match: dict[str, Any] = {"employee_id": employee_id}
    date_filter: dict[str, str] = {}
    if start_date:
        date_filter["$gte"] = start_date.isoformat()
    if end_date:
        date_filter["$lte"] = end_date.isoformat()
    if date_filter:
        match["work_date"] = date_filter
    pipeline = [
        {"$match": match},
        {"$group": {"_id": "$employee_id", "days_recorded": {"$sum": 1},
            "completed_shifts": {"$sum": {"$cond": [{"$ne": ["$punch_out", None]}, 1, 0]}},
            "total_minutes": {"$sum": {"$ifNull": ["$total_minutes", 0]}},
            "average_minutes": {"$avg": "$total_minutes"}}},
        {"$project": {"_id": 0, "employee_id": "$_id", "days_recorded": 1,
            "completed_shifts": 1, "total_minutes": 1,
            "average_minutes": {"$round": [{"$ifNull": ["$average_minutes", 0]}, 2]}}},
    ]
    result = list(attendance.aggregate(pipeline))
    return result[0] if result else {"employee_id": employee_id, "days_recorded": 0,
        "completed_shifts": 0, "total_minutes": 0, "average_minutes": 0}
