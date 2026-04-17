"""Schedules endpoints for workout schedule information."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from wodplanner.app.dependencies import get_schedule_service
from wodplanner.models.schedule import ScheduleResponse
from wodplanner.services.schedule import ScheduleService

router = APIRouter(prefix="/schedules", tags=["schedules"])


def _schedule_to_response(schedule) -> ScheduleResponse:
    """Convert a Schedule model to response model."""
    return ScheduleResponse(
        date=schedule.date,
        class_type=schedule.class_type,
        warmup_mobility=schedule.warmup_mobility,
        strength_specialty=schedule.strength_specialty,
        metcon=schedule.metcon,
    )


@router.get("/{schedule_date}", response_model=list[ScheduleResponse])
def get_schedules_by_date(
    schedule_date: date,
    service: ScheduleService = Depends(get_schedule_service),
) -> list[ScheduleResponse]:
    """Get all workout schedules for a specific date."""
    schedules = service.get_by_date(schedule_date)
    return [_schedule_to_response(s) for s in schedules]


@router.get("/{schedule_date}/{class_type}", response_model=ScheduleResponse)
def get_schedule_by_date_and_class(
    schedule_date: date,
    class_type: str,
    service: ScheduleService = Depends(get_schedule_service),
) -> ScheduleResponse:
    """Get workout schedule for a specific date and class type."""
    schedule = service.get_by_date_and_class(schedule_date, class_type)
    if not schedule:
        raise HTTPException(
            status_code=404,
            detail=f"No schedule found for {class_type} on {schedule_date}",
        )
    return _schedule_to_response(schedule)
