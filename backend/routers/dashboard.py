# Dashboard API Router

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.security import HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging

from ..database import get_db, get_user_by_id, get_recent_health_records, get_recent_safety_records
from ..models import User, Alert, AlertPriority, AlertType, Reminder
from ..agents.coordinator import agent_coordinator
from ..config import settings

router = APIRouter()
security = HTTPBearer()
logger = logging.getLogger(__name__)

@router.get("/overview/{user_id}")
async def get_dashboard_overview(
    user_id: int,
    hours: int = Query(24, description="Time period in hours for overview", ge=1, le=168),
    db: AsyncSession = Depends(get_db)
):
    """Get comprehensive dashboard overview for a user"""
    try:
        # Validate user exists
        user = await get_user_by_id(user_id, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )

        # Get time range
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)

        # Get health data summary
        health_summary = await _get_health_summary(user_id, cutoff_time, db)

        # Get safety data summary
        safety_summary = await _get_safety_summary(user_id, cutoff_time, db)

        # Get alerts summary
        alerts_summary = await _get_alerts_summary(user_id, cutoff_time, db)

        # Get reminders summary
        reminders_summary = await _get_reminders_summary(user_id, db)

        # Get system status
        system_status = await _get_system_status()

        return {
            "user_id": user_id,
            "user_info": {
                "full_name": user.full_name,
                "role": user.role.value,
                "device_id": user.device_id,
                "is_active": user.is_active
            },
            "time_period_hours": hours,
            "health_summary": health_summary,
            "safety_summary": safety_summary,
            "alerts_summary": alerts_summary,
            "reminders_summary": reminders_summary,
            "system_status": system_status,
            "generated_at": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating dashboard overview: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate dashboard overview"
        )

@router.get("/caregiver/{caregiver_id}")
async def get_caregiver_dashboard(
    caregiver_id: int,
    hours: int = Query(24, description="Time period in hours", ge=1, le=168),
    db: AsyncSession = Depends(get_db)
):
    """Get caregiver dashboard with all assigned elderly users"""
    try:
        # Validate caregiver exists
        caregiver = await get_user_by_id(caregiver_id, db)
        if not caregiver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Caregiver {caregiver_id} not found"
            )

        # Get assigned elderly users
        from sqlalchemy import select
        from ..models import CaregiverElderlyMapping

        result = await db.execute(
            select(CaregiverElderlyMapping, User)
            .join(User, CaregiverElderlyMapping.elderly_id == User.id)
            .where(CaregiverElderlyMapping.caregiver_id == caregiver_id)
        )

        elderly_users = []
        for mapping, elderly in result:
            elderly_users.append({
                "user_id": elderly.id,
                "full_name": elderly.full_name,
                "device_id": elderly.device_id,
                "relationship_type": mapping.relationship_type,
                "is_primary_caregiver": mapping.is_primary_caregiver,
                "assigned_at": mapping.created_at.isoformat()
            })

        # Get summary for each elderly user
        elderly_summaries = []
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)

        for elderly_info in elderly_users:
            user_id = elderly_info["user_id"]

            # Get recent data for each user
            health_data = await get_recent_health_records(user_id, limit=10, session=db)
            safety_data = await get_recent_safety_records(user_id, limit=10, session=db)

            # Calculate quick summary
            summary = {
                "user_id": user_id,
                "full_name": elderly_info["full_name"],
                "health_alerts": sum(1 for r in health_data if r.overall_health_alert),
                "safety_alerts": sum(1 for r in safety_data if r.safety_alert),
                "last_health_update": max((r.timestamp for r in health_data), default=None),
                "last_safety_update": max((r.timestamp for r in safety_data), default=None),
                "relationship_type": elderly_info["relationship_type"]
            }

            elderly_summaries.append(summary)

        # Get overall alerts for caregiver
        alerts_result = await db.execute(
            select(Alert).where(
                Alert.user_id.in_([u["user_id"] for u in elderly_users]),
                Alert.created_at >= cutoff_time,
                Alert.is_resolved == False
            ).order_by(Alert.created_at.desc()).limit(20)
        )
        recent_alerts = alerts_result.scalars().all()

        return {
            "caregiver_id": caregiver_id,
            "caregiver_name": caregiver.full_name,
            "total_elderly": len(elderly_users),
            "elderly_users": elderly_summaries,
            "recent_alerts": [
                {
                    "id": alert.id,
                    "user_id": alert.user_id,
                    "alert_type": alert.alert_type.value,
                    "priority": alert.priority.value,
                    "title": alert.title,
                    "created_at": alert.created_at.isoformat()
                }
                for alert in recent_alerts
            ],
            "system_status": await _get_system_status(),
            "generated_at": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating caregiver dashboard: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate caregiver dashboard"
        )

@router.get("/realtime/{user_id}")
async def get_realtime_data(
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get real-time data snapshot for a user"""
    try:
        # Validate user exists
        user = await get_user_by_id(user_id, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )

        # Get latest health record
        health_records = await get_recent_health_records(user_id, limit=1, session=db)
        latest_health = health_records[0] if health_records else None

        # Get latest safety record
        safety_records = await get_recent_safety_records(user_id, limit=1, session=db)
        latest_safety = safety_records[0] if safety_records else None

        # Get active alerts
        from sqlalchemy import select
        alerts_result = await db.execute(
            select(Alert).where(
                Alert.user_id == user_id,
                Alert.is_resolved == False
            ).order_by(Alert.priority.desc()).limit(5)
        )
        active_alerts = alerts_result.scalars().all()

        # Get pending reminders
        reminders_result = await db.execute(
            select(Reminder).where(
                Reminder.user_id == user_id,
                Reminder.is_acknowledged == False,
                Reminder.scheduled_time <= datetime.utcnow()
            ).order_by(Reminder.scheduled_time.asc()).limit(5)
        )
        pending_reminders = reminders_result.scalars().all()

        return {
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat(),
            "latest_health": {
                "timestamp": latest_health.timestamp.isoformat() if latest_health else None,
                "heart_rate": latest_health.heart_rate if latest_health else None,
                "blood_pressure": f"{latest_health.blood_pressure_systolic}/{latest_health.blood_pressure_diastolic}" if latest_health and latest_health.blood_pressure_systolic else None,
                "glucose_level": latest_health.glucose_level if latest_health else None,
                "oxygen_saturation": latest_health.oxygen_saturation if latest_health else None,
                "overall_alert": latest_health.overall_health_alert if latest_health else False
            } if latest_health else None,
            "latest_safety": {
                "timestamp": latest_safety.timestamp.isoformat() if latest_safety else None,
                "movement_activity": latest_safety.movement_activity.value if latest_safety and latest_safety.movement_activity else None,
                "location_room": latest_safety.location_room if latest_safety else None,
                "fall_detected": latest_safety.fall_detected if latest_safety else False,
                "safety_alert": latest_safety.safety_alert if latest_safety else False
            } if latest_safety else None,
            "active_alerts": [
                {
                    "id": alert.id,
                    "type": alert.alert_type.value,
                    "priority": alert.priority.value,
                    "title": alert.title,
                    "created_at": alert.created_at.isoformat()
                }
                for alert in active_alerts
            ],
            "pending_reminders": [
                {
                    "id": reminder.id,
                    "type": reminder.reminder_type.value,
                    "title": reminder.title,
                    "scheduled_time": reminder.scheduled_time.isoformat(),
                    "escalation_attempts": reminder.escalation_attempts
                }
                for reminder in pending_reminders
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving real-time data: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve real-time data"
        )

@router.get("/analytics/{user_id}")
async def get_analytics_data(
    user_id: int,
    days: int = Query(30, description="Number of days for analytics", ge=1, le=365),
    db: AsyncSession = Depends(get_db)
):
    """Get analytics data for dashboard charts"""
    try:
        # Validate user exists
        user = await get_user_by_id(user_id, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )

        # Get time range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        # Get health records for analytics
        health_records = await get_recent_health_records(user_id, limit=1000, session=db)
        health_records = [r for r in health_records if start_date <= r.timestamp <= end_date]

        # Get safety records for analytics
        safety_records = await get_recent_safety_records(user_id, limit=1000, session=db)
        safety_records = [r for r in safety_records if start_date <= r.timestamp <= end_date]

        # Generate analytics data
        analytics = await _generate_analytics_data(health_records, safety_records, days)

        return {
            "user_id": user_id,
            "time_period_days": days,
            "analytics": analytics,
            "generated_at": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating analytics data: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate analytics data"
        )

async def _get_health_summary(user_id: int, cutoff_time: datetime, db: AsyncSession) -> Dict[str, Any]:
    """Get health summary for dashboard"""
    health_records = await get_recent_health_records(user_id, limit=100, session=db)
    recent_records = [r for r in health_records if r.timestamp >= cutoff_time]

    if not recent_records:
        return {
            "total_records": 0,
            "latest_vitals": None,
            "alerts_count": 0,
            "status": "no_data"
        }

    latest = max(recent_records, key=lambda r: r.timestamp)

    return {
        "total_records": len(recent_records),
        "latest_vitals": {
            "timestamp": latest.timestamp.isoformat(),
            "heart_rate": latest.heart_rate,
            "blood_pressure": f"{latest.blood_pressure_systolic}/{latest.blood_pressure_diastolic}",
            "glucose_level": latest.glucose_level,
            "oxygen_saturation": latest.oxygen_saturation
        },
        "alerts_count": sum(1 for r in recent_records if r.overall_health_alert),
        "status": "alert" if latest.overall_health_alert else "normal"
    }

async def _get_safety_summary(user_id: int, cutoff_time: datetime, db: AsyncSession) -> Dict[str, Any]:
    """Get safety summary for dashboard"""
    safety_records = await get_recent_safety_records(user_id, limit=100, session=db)
    recent_records = [r for r in safety_records if r.timestamp >= cutoff_time]

    if not recent_records:
        return {
            "total_records": 0,
            "latest_activity": None,
            "falls_count": 0,
            "status": "no_data"
        }

    latest = max(recent_records, key=lambda r: r.timestamp)

    return {
        "total_records": len(recent_records),
        "latest_activity": {
            "timestamp": latest.timestamp.isoformat(),
            "movement_activity": latest.movement_activity.value if latest.movement_activity else None,
            "location_room": latest.location_room,
            "fall_detected": latest.fall_detected
        },
        "falls_count": sum(1 for r in recent_records if r.fall_detected),
        "alerts_count": sum(1 for r in recent_records if r.safety_alert),
        "status": "alert" if latest.safety_alert else "normal"
    }

async def _get_alerts_summary(user_id: int, cutoff_time: datetime, db: AsyncSession) -> Dict[str, Any]:
    """Get alerts summary for dashboard"""
    from sqlalchemy import select

    result = await db.execute(
        select(Alert).where(
            Alert.user_id == user_id,
            Alert.created_at >= cutoff_time
        )
    )
    alerts = result.scalars().all()

    return {
        "total_alerts": len(alerts),
        "by_priority": {
            "low": sum(1 for a in alerts if a.priority == AlertPriority.LOW),
            "medium": sum(1 for a in alerts if a.priority == AlertPriority.MEDIUM),
            "high": sum(1 for a in alerts if a.priority == AlertPriority.HIGH),
            "critical": sum(1 for a in alerts if a.priority == AlertPriority.CRITICAL)
        },
        "by_type": {
            "health": sum(1 for a in alerts if a.alert_type == AlertType.HEALTH),
            "safety": sum(1 for a in alerts if a.alert_type == AlertType.SAFETY),
            "reminder": sum(1 for a in alerts if a.alert_type == AlertType.REMINDER),
            "system": sum(1 for a in alerts if a.alert_type == AlertType.SYSTEM)
        },
        "unresolved": sum(1 for a in alerts if not a.is_resolved)
    }

async def _get_reminders_summary(user_id: int, db: AsyncSession) -> Dict[str, Any]:
    """Get reminders summary for dashboard"""
    from sqlalchemy import select

    # Get recent reminders (last 7 days)
    week_ago = datetime.utcnow() - timedelta(days=7)
    result = await db.execute(
        select(Reminder).where(
            Reminder.user_id == user_id,
            Reminder.created_at >= week_ago
        )
    )
    reminders = result.scalars().all()

    return {
        "total_reminders": len(reminders),
        "completed": sum(1 for r in reminders if r.is_acknowledged),
        "pending": sum(1 for r in reminders if not r.is_acknowledged and r.scheduled_time <= datetime.utcnow()),
        "upcoming": sum(1 for r in reminders if not r.is_acknowledged and r.scheduled_time > datetime.utcnow()),
        "by_type": {
            "medication": sum(1 for r in reminders if r.reminder_type.value == "medication"),
            "appointment": sum(1 for r in reminders if r.reminder_type.value == "appointment"),
            "exercise": sum(1 for r in reminders if r.reminder_type.value == "exercise"),
            "hydration": sum(1 for r in reminders if r.reminder_type.value == "hydration"),
            "meal": sum(1 for r in reminders if r.reminder_type.value == "meal"),
            "social_activity": sum(1 for r in reminders if r.reminder_type.value == "social_activity"),
            "other": sum(1 for r in reminders if r.reminder_type.value == "other")
        }
    }

async def _get_system_status() -> Dict[str, Any]:
    """Get system status for dashboard"""
    try:
        system_status = await agent_coordinator.get_agent_status()
        return {
            "agents_running": system_status.get("running_agents", []),
            "agents_total": system_status.get("total_agents", 0),
            "system_health": "healthy" if system_status.get("total_agents", 0) > 0 else "degraded",
            "last_updated": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting system status: {e}")
        return {
            "agents_running": [],
            "agents_total": 0,
            "system_health": "error",
            "last_updated": datetime.utcnow().isoformat()
        }

async def _generate_analytics_data(health_records: List, safety_records: List, days: int) -> Dict[str, Any]:
    """Generate analytics data for charts"""
    analytics = {
        "health_trends": [],
        "safety_patterns": [],
        "alerts_timeline": [],
        "activity_distribution": {}
    }

    # Health trends (daily averages)
    if health_records:
        # Group by day
        daily_health = {}
        for record in health_records:
            day = record.timestamp.date()
            if day not in daily_health:
                daily_health[day] = []
            daily_health[day].append(record)

        for day, records in sorted(daily_health.items()):
            heart_rates = [r.heart_rate for r in records if r.heart_rate]
            avg_hr = sum(heart_rates) / len(heart_rates) if heart_rates else 0

            analytics["health_trends"].append({
                "date": day.isoformat(),
                "average_heart_rate": round(avg_hr, 1),
                "records_count": len(records),
                "alerts_count": sum(1 for r in records if r.overall_health_alert)
            })

    # Safety patterns
    if safety_records:
        # Group by day
        daily_safety = {}
        for record in safety_records:
            day = record.timestamp.date()
            if day not in daily_safety:
                daily_safety[day] = []
            daily_safety[day].append(record)

        for day, records in sorted(daily_safety.items()):
            falls_count = sum(1 for r in records if r.fall_detected)
            analytics["safety_patterns"].append({
                "date": day.isoformat(),
                "records_count": len(records),
                "falls_count": falls_count,
                "alerts_count": sum(1 for r in records if r.safety_alert)
            })

    # Activity distribution
    if safety_records:
        activity_counts = {}
        for record in safety_records:
            activity = record.movement_activity.value if record.movement_activity else "unknown"
            activity_counts[activity] = activity_counts.get(activity, 0) + 1

        total_activities = sum(activity_counts.values())
        analytics["activity_distribution"] = {
            activity: {
                "count": count,
                "percentage": round((count / total_activities) * 100, 1)
            }
            for activity, count in activity_counts.items()
        }

    return analytics
