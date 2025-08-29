# Reminders API Router

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.security import HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging

from ..database import get_db, get_user_by_id
from ..models import User, Reminder, ReminderType
from ..agents.coordinator import agent_coordinator
from ..config import settings

router = APIRouter()
security = HTTPBearer()
logger = logging.getLogger(__name__)

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_reminder(
    reminder_data: Dict[str, Any],
    user_id: int = Query(..., description="User ID"),
    db: AsyncSession = Depends(get_db)
):
    """Create a new reminder for a user"""
    try:
        # Validate user exists
        user = await get_user_by_id(user_id, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )

        # Create reminder through agent
        reminder = await agent_coordinator.create_reminder(user_id, reminder_data)

        if not reminder:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create reminder"
            )

        return {
            "message": "Reminder created successfully",
            "reminder_id": reminder.id,
            "user_id": user_id,
            "scheduled_time": reminder.scheduled_time.isoformat(),
            "reminder_type": reminder.reminder_type.value,
            "title": reminder.title
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating reminder: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create reminder"
        )

@router.get("/{user_id}")
async def get_user_reminders(
    user_id: int,
    limit: int = Query(50, description="Number of reminders to retrieve", ge=1, le=500),
    include_completed: bool = Query(True, description="Include completed reminders"),
    reminder_type: Optional[str] = Query(None, description="Filter by reminder type"),
    db: AsyncSession = Depends(get_db)
):
    """Get reminders for a user"""
    try:
        # Validate user exists
        user = await get_user_by_id(user_id, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )

        # Get reminders from agent
        if "reminder" in agent_coordinator.agents:
            reminders = await agent_coordinator.agents["reminder"].get_user_reminders(user_id)
        else:
            reminders = []

        # Apply filters
        if not include_completed:
            reminders = [r for r in reminders if not r["is_acknowledged"]]

        if reminder_type:
            try:
                filter_type = ReminderType(reminder_type)
                reminders = [r for r in reminders if r["type"] == filter_type.value]
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid reminder type: {reminder_type}"
                )

        # Sort by scheduled time
        reminders.sort(key=lambda x: x["scheduled_time"], reverse=True)

        # Apply limit
        reminders = reminders[:limit]

        return {
            "user_id": user_id,
            "total_reminders": len(reminders),
            "reminders": reminders
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving reminders: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve reminders"
        )

@router.put("/{reminder_id}/acknowledge")
async def acknowledge_reminder(
    reminder_id: int,
    user_id: int = Query(..., description="User ID"),
    db: AsyncSession = Depends(get_db)
):
    """Acknowledge a reminder"""
    try:
        # Validate user exists
        user = await get_user_by_id(user_id, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )

        # Acknowledge reminder through agent
        if "reminder" in agent_coordinator.agents:
            success = await agent_coordinator.agents["reminder"].acknowledge_reminder(reminder_id, user_id)
        else:
            success = False

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reminder {reminder_id} not found or already acknowledged"
            )

        return {
            "message": "Reminder acknowledged successfully",
            "reminder_id": reminder_id,
            "user_id": user_id,
            "acknowledged_at": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error acknowledging reminder: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to acknowledge reminder"
        )

@router.get("/types")
async def get_reminder_types():
    """Get available reminder types"""
    return {
        "reminder_types": [
            {
                "value": reminder_type.value,
                "label": reminder_type.value.replace("_", " ").title(),
                "description": _get_reminder_type_description(reminder_type)
            }
            for reminder_type in ReminderType
        ]
    }

@router.get("/stats/{user_id}")
async def get_reminder_stats(
    user_id: int,
    days: int = Query(30, description="Number of days to analyze", ge=1, le=365),
    db: AsyncSession = Depends(get_db)
):
    """Get reminder statistics for a user"""
    try:
        # Validate user exists
        user = await get_user_by_id(user_id, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )

        # Get reminders from agent
        if "reminder" in agent_coordinator.agents:
            all_reminders = await agent_coordinator.agents["reminder"].get_user_reminders(user_id)
        else:
            all_reminders = []

        # Filter by time period
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        recent_reminders = [
            r for r in all_reminders
            if datetime.fromisoformat(r["scheduled_time"].replace('Z', '+00:00')) >= cutoff_date
        ]

        # Calculate statistics
        stats = await _calculate_reminder_stats(recent_reminders)

        return {
            "user_id": user_id,
            "time_period_days": days,
            "total_reminders": len(recent_reminders),
            "statistics": stats
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating reminder stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to calculate reminder statistics"
        )

@router.post("/bulk")
async def create_bulk_reminders(
    reminders_data: List[Dict[str, Any]],
    user_id: int = Query(..., description="User ID"),
    db: AsyncSession = Depends(get_db)
):
    """Create multiple reminders at once"""
    try:
        # Validate user exists
        user = await get_user_by_id(user_id, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )

        created_reminders = []
        failed_reminders = []

        for i, reminder_data in enumerate(reminders_data):
            try:
                reminder = await agent_coordinator.create_reminder(user_id, reminder_data)
                if reminder:
                    created_reminders.append({
                        "index": i,
                        "reminder_id": reminder.id,
                        "scheduled_time": reminder.scheduled_time.isoformat(),
                        "type": reminder.reminder_type.value,
                        "title": reminder.title
                    })
                else:
                    failed_reminders.append({
                        "index": i,
                        "error": "Failed to create reminder",
                        "data": reminder_data
                    })
            except Exception as e:
                failed_reminders.append({
                    "index": i,
                    "error": str(e),
                    "data": reminder_data
                })

        return {
            "message": f"Created {len(created_reminders)} reminders, {len(failed_reminders)} failed",
            "user_id": user_id,
            "created": created_reminders,
            "failed": failed_reminders
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating bulk reminders: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create bulk reminders"
        )

@router.get("/settings")
async def get_reminder_settings():
    """Get reminder system settings"""
    return {
        "reminder_settings": {
            "retry_attempts": settings.reminder_retry_attempts,
            "escalation_minutes": settings.reminder_escalation_minutes,
            "voice_enabled": settings.voice_reminder_enabled,
            "max_escalation_attempts": 3
        },
        "notification_channels": {
            "websocket": True,
            "sms": bool(settings.twilio_phone_number),
            "email": bool(settings.sendgrid_api_key),
            "voice": bool(settings.twilio_phone_number)
        },
        "supported_types": [rt.value for rt in ReminderType]
    }

def _get_reminder_type_description(reminder_type: ReminderType) -> str:
    """Get description for reminder type"""
    descriptions = {
        ReminderType.MEDICATION: "Medication intake reminders",
        ReminderType.APPOINTMENT: "Medical or personal appointments",
        ReminderType.EXERCISE: "Physical activity and exercise reminders",
        ReminderType.HYDRATION: "Water intake and hydration reminders",
        ReminderType.MEAL: "Meal times and nutrition reminders",
        ReminderType.SOCIAL_ACTIVITY: "Social activities and family time",
        ReminderType.OTHER: "Custom reminders"
    }
    return descriptions.get(reminder_type, "Custom reminder")

async def _calculate_reminder_stats(reminders: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate reminder statistics"""
    if not reminders:
        return {
            "completion_rate": 0,
            "total_completed": 0,
            "total_pending": 0,
            "type_breakdown": {},
            "average_acknowledgment_time": None
        }

    # Basic counts
    completed = [r for r in reminders if r["is_acknowledged"]]
    pending = [r for r in reminders if not r["is_acknowledged"]]

    # Completion rate
    completion_rate = round((len(completed) / len(reminders)) * 100, 1)

    # Type breakdown
    type_counts = {}
    type_completed = {}

    for reminder in reminders:
        rtype = reminder["type"]
        type_counts[rtype] = type_counts.get(rtype, 0) + 1

        if reminder["is_acknowledged"]:
            type_completed[rtype] = type_completed.get(rtype, 0) + 1

    type_breakdown = {}
    for rtype, total in type_counts.items():
        completed_count = type_completed.get(rtype, 0)
        type_breakdown[rtype] = {
            "total": total,
            "completed": completed_count,
            "completion_rate": round((completed_count / total) * 100, 1) if total > 0 else 0
        }

    # Average acknowledgment time (for completed reminders)
    acknowledgment_times = []
    for reminder in completed:
        if reminder["acknowledged_at"]:
            scheduled = datetime.fromisoformat(reminder["scheduled_time"].replace('Z', '+00:00'))
            acknowledged = datetime.fromisoformat(reminder["acknowledged_at"].replace('Z', '+00:00'))
            time_diff = (acknowledged - scheduled).total_seconds() / 60  # minutes
            acknowledgment_times.append(time_diff)

    avg_ack_time = None
    if acknowledgment_times:
        avg_ack_time = round(sum(acknowledgment_times) / len(acknowledgment_times), 1)

    return {
        "completion_rate": completion_rate,
        "total_completed": len(completed),
        "total_pending": len(pending),
        "type_breakdown": type_breakdown,
        "average_acknowledgment_time": avg_ack_time
    }
