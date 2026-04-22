"""Pydantic schemas for the presence/attendance module."""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.presence_app.constants import ScanMethod, ScanType


# ---------------------------------------------------------------------------
# Presence
# ---------------------------------------------------------------------------


class PresenceResponse(BaseModel):
    id: int
    user_id: int
    date_scan: date
    heure_scan: time
    method: ScanMethod
    scan_type: ScanType
    is_late: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaginatedPresence(BaseModel):
    items: list[PresenceResponse]
    total: int
    skip: int
    limit: int


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------


class ScanRequest(BaseModel):
    """Payload sent by the client when a user scans.

    The server decides automatically whether the scan is ENTRY or EXIT,
    computes late status and enforces the max-2-scans-per-day rule.
    """

    user_id: int = Field(..., gt=0)
    method: ScanMethod
    # Optional scan timestamp. If omitted, server time is used.
    scanned_at: Optional[datetime] = None


class ScanResponse(BaseModel):
    presence: PresenceResponse
    message: str


# ---------------------------------------------------------------------------
# WorkSchedule
# ---------------------------------------------------------------------------


class WorkScheduleBase(BaseModel):
    user_id: Optional[int] = Field(
        default=None,
        description="If null, this is the global default schedule.",
    )
    start_time: time
    end_time: time
    break_start: Optional[time] = None
    break_end: Optional[time] = None

    @model_validator(mode="after")
    def _validate_ranges(self) -> "WorkScheduleBase":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be strictly after start_time")
        if (self.break_start is None) ^ (self.break_end is None):
            raise ValueError("break_start and break_end must both be set or both null")
        if self.break_start and self.break_end:
            if self.break_end <= self.break_start:
                raise ValueError("break_end must be strictly after break_start")
            if self.break_start < self.start_time or self.break_end > self.end_time:
                raise ValueError("break must be within the work day")
        return self


class WorkScheduleCreate(WorkScheduleBase):
    pass


class WorkScheduleUpdate(BaseModel):
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    break_start: Optional[time] = None
    break_end: Optional[time] = None


class WorkScheduleResponse(WorkScheduleBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


class DailyStat(BaseModel):
    date: date
    count: int
    user_ids: list[int]


class RangeStatResponse(BaseModel):
    start: date
    end: date
    total: int
    per_day: list[DailyStat]


class TodayStatResponse(BaseModel):
    date: date
    count: int
    user_ids: list[int]