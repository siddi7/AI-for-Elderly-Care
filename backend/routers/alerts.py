# Alerts API Router

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.security import HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging

from ..database import get_db, get_user_by_id
from ..models import User, Alert, AlertPriority, AlertType
from ..config import settings

router = APIRouter()
security = HTTPBearer()
logger = logging.getLogger(__name__)

@router.get("/{user_id}")
async def get_user_alerts(
    user_id: int,
    limit: int = Query(50, description="Number of alerts to retrieve", ge=1, le=500),
    hours: Optional[int] = Query(None, description="Get alerts from last N hours"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    alert_type: Optional[str] = Query(None, description="Filter by alert type"),
    resolved: Optional[bool] = Query(None, description="Filter by resolution status"),
    db: AsyncSession = Depends(get_db)
):
    """Get alerts for a user"""
    try:
        # Validate user exists
        user = await get_user_by_id(user_id, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )

        # Build query
        from sqlalchemy import select

        query = select(Alert).where(Alert.user_id == user_id)

        # Apply filters
        if hours:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)
            query = query.where(Alert.created_at >= cutoff_time)

        if priority:
            try:
                priority_enum = AlertPriority(priority)
                query = query.where(Alert.priority == priority_enum)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid priority: {priority}"
                )

        if alert_type:
            try:
                type_enum = AlertType(alert_type)
                query = query.where(Alert.alert_type == type_enum)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid alert type: {alert_type}"
                )

        if resolved is not None:
            query = query.where(Alert.is_resolved == resolved)

        # Execute query
        result = await db.execute(
            query.order_by(Alert.created_at.desc()).limit(limit)
        )
        alerts = result.scalars().all()

        # Convert to response format
        alert_list = []
        for alert in alerts:
            alert_list.append({
                "id": alert.id,
                "alert_type": alert.alert_type.value,
                "priority": alert.priority.value,
                "title": alert.title,
                "message": alert.message,
                "related_record_id": alert.related_record_id,
                "is_resolved": alert.is_resolved,
                "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
                "resolved_by": alert.resolved_by,
                "resolution_notes": alert.resolution_notes,
                "created_at": alert.created_at.isoformat(),
                "updated_at": alert.updated_at.isoformat(),
                "notifications": {
                    "email_sent": alert.email_sent,
                    "sms_sent": alert.sms_sent,
                    "push_sent": alert.push_sent,
                    "voice_call_made": alert.voice_call_made
                }
            })

        return {
            "user_id": user_id,
            "total_alerts": len(alert_list),
            "alerts": alert_list
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving alerts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve alerts"
        )

@router.put("/{alert_id}/resolve")
async def resolve_alert(
    alert_id: int,
    resolution_data: Dict[str, Any],
    user_id: int = Query(..., description="User ID resolving the alert"),
    db: AsyncSession = Depends(get_db)
):
    """Resolve an alert"""
    try:
        # Validate user exists
        user = await get_user_by_id(user_id, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )

        # Get alert
        from sqlalchemy import select
        result = await db.execute(
            select(Alert).where(Alert.id == alert_id)
        )
        alert = result.scalar_one_or_none()

        if not alert:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alert {alert_id} not found"
            )

        # Update alert
        alert.is_resolved = True
        alert.resolved_at = datetime.utcnow()
        alert.resolved_by = user_id
        alert.resolution_notes = resolution_data.get("notes", "")

        await db.commit()

        return {
            "message": "Alert resolved successfully",
            "alert_id": alert_id,
            "resolved_by": user_id,
            "resolved_at": alert.resolved_at.isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resolving alert: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to resolve alert"
        )

@router.get("/stats/{user_id}")
async def get_alert_stats(
    user_id: int,
    days: int = Query(30, description="Number of days to analyze", ge=1, le=365),
    db: AsyncSession = Depends(get_db)
):
    """Get alert statistics for a user"""
    try:
        # Validate user exists
        user = await get_user_by_id(user_id, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )

        # Get alerts from time period
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        from sqlalchemy import select, func

        result = await db.execute(
            select(Alert).where(
                Alert.user_id == user_id,
                Alert.created_at >= cutoff_date
            )
        )
        alerts = result.scalars().all()

        # Calculate statistics
        stats = await _calculate_alert_stats(alerts)

        return {
            "user_id": user_id,
            "time_period_days": days,
            "total_alerts": len(alerts),
            "statistics": stats
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating alert stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to calculate alert statistics"
        )

@router.get("/summary/{user_id}")
async def get_alert_summary(
    user_id: int,
    hours: int = Query(24, description="Time period in hours", ge=1, le=168),
    db: AsyncSession = Depends(get_db)
):
    """Get alert summary for a user"""
    try:
        # Validate user exists
        user = await get_user_by_id(user_id, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )

        # Get recent alerts
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        from sqlalchemy import select

        result = await db.execute(
            select(Alert).where(
                Alert.user_id == user_id,
                Alert.created_at >= cutoff_time
            ).order_by(Alert.created_at.desc())
        )
        alerts = result.scalars().all()

        # Group by priority and type
        summary = {
            "total_alerts": len(alerts),
            "by_priority": {},
            "by_type": {},
            "unresolved": 0,
            "critical_unresolved": 0
        }

        for alert in alerts:
            # Count by priority
            priority = alert.priority.value
            summary["by_priority"][priority] = summary["by_priority"].get(priority, 0) + 1

            # Count by type
            alert_type = alert.alert_type.value
            summary["by_type"][alert_type] = summary["by_type"].get(alert_type, 0) + 1

            # Count unresolved
            if not alert.is_resolved:
                summary["unresolved"] += 1
                if alert.priority == AlertPriority.CRITICAL:
                    summary["critical_unresolved"] += 1

        return {
            "user_id": user_id,
            "time_period_hours": hours,
            "summary": summary
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating alert summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate alert summary"
        )

@router.post("/test")
async def test_alert_system(
    alert_data: Dict[str, Any],
    user_id: int = Query(..., description="User ID for test alert"),
    db: AsyncSession = Depends(get_db)
):
    """Create a test alert (for system testing)"""
    try:
        # Validate user exists
        user = await get_user_by_id(user_id, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )

        # Create test alert
        test_alert = Alert(
            user_id=user_id,
            alert_type=AlertType.SYSTEM,
            priority=AlertPriority.LOW,
            title="System Test Alert",
            message="This is a test alert to verify the alert system is working correctly."
        )

        db.add(test_alert)
        await db.commit()
        await db.refresh(test_alert)

        return {
            "message": "Test alert created successfully",
            "alert_id": test_alert.id,
            "user_id": user_id,
            "created_at": test_alert.created_at.isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating test alert: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create test alert"
        )

@router.get("/types")
async def get_alert_types():
    """Get available alert types and priorities"""
    return {
        "alert_types": [
            {
                "value": alert_type.value,
                "label": alert_type.value.replace("_", " ").title(),
                "description": _get_alert_type_description(alert_type)
            }
            for alert_type in AlertType
        ],
        "priorities": [
            {
                "value": priority.value,
                "label": priority.value.title(),
                "description": _get_priority_description(priority)
            }
            for priority in AlertPriority
        ]
    }

@router.get("/settings")
async def get_alert_settings():
    """Get alert system settings"""
    return {
        "alert_settings": {
            "retry_attempts": settings.alert_retry_attempts,
            "escalation_minutes": settings.alert_escalation_minutes,
            "emergency_contacts_required": settings.emergency_contacts_required
        },
        "notification_providers": {
            "email": bool(settings.sendgrid_api_key),
            "sms": bool(settings.twilio_phone_number),
            "voice": bool(settings.twilio_phone_number),
            "websocket": True
        },
        "escalation_levels": {
            "max_level": 3,
            "level_descriptions": {
                0: "Initial notification",
                1: "First escalation - additional notifications",
                2: "Second escalation - emergency contacts",
                3: "Final escalation - emergency services"
            }
        }
    }

def _get_alert_type_description(alert_type: AlertType) -> str:
    """Get description for alert type"""
    descriptions = {
        AlertType.HEALTH: "Health monitoring alerts (vital signs, thresholds)",
        AlertType.SAFETY: "Safety monitoring alerts (falls, inactivity)",
        AlertType.REMINDER: "Reminder alerts (medications, appointments)",
        AlertType.SYSTEM: "System alerts (agent status, connectivity)"
    }
    return descriptions.get(alert_type, "General alert")

def _get_priority_description(priority: AlertPriority) -> str:
    """Get description for alert priority"""
    descriptions = {
        AlertPriority.LOW: "Low priority - informational alerts",
        AlertPriority.MEDIUM: "Medium priority - requires attention",
        AlertPriority.HIGH: "High priority - urgent attention needed",
        AlertPriority.CRITICAL: "Critical priority - immediate action required"
    }
    return descriptions.get(priority, "Unknown priority")

async def _calculate_alert_stats(alerts: List[Alert]) -> Dict[str, Any]:
    """Calculate alert statistics"""
    if not alerts:
        return {
            "total_alerts": 0,
            "resolved_rate": 0,
            "average_resolution_time": None,
            "by_priority": {},
            "by_type": {},
            "notification_stats": {}
        }

    # Basic counts
    resolved = [a for a in alerts if a.is_resolved]
    unresolved = [a for a in alerts if not a.is_resolved]

    resolved_rate = round((len(resolved) / len(alerts)) * 100, 1)

    # Priority breakdown
    priority_counts = {}
    for alert in alerts:
        priority = alert.priority.value
        priority_counts[priority] = priority_counts.get(priority, 0) + 1

    # Type breakdown
    type_counts = {}
    for alert in alerts:
        alert_type = alert.alert_type.value
        type_counts[alert_type] = type_counts.get(alert_type, 0) + 1

    # Resolution time analysis
    resolution_times = []
    for alert in resolved:
        if alert.resolved_at:
            time_diff = (alert.resolved_at - alert.created_at).total_seconds() / 3600  # hours
            resolution_times.append(time_diff)

    avg_resolution_time = None
    if resolution_times:
        avg_resolution_time = round(sum(resolution_times) / len(resolution_times), 1)

    # Notification stats
    notification_stats = {
        "email_sent": sum(1 for a in alerts if a.email_sent),
        "sms_sent": sum(1 for a in alerts if a.sms_sent),
        "push_sent": sum(1 for a in alerts if a.push_sent),
        "voice_call_made": sum(1 for a in alerts if a.voice_call_made)
    }

    return {
        "total_alerts": len(alerts),
        "resolved_count": len(resolved),
        "unresolved_count": len(unresolved),
        "resolved_rate": resolved_rate,
        "average_resolution_time": avg_resolution_time,
        "by_priority": priority_counts,
        "by_type": type_counts,
        "notification_stats": notification_stats
    }
