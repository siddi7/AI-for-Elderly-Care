# Safety Monitoring API Router

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.security import HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging

from ..database import get_db, create_safety_record, get_recent_safety_records, get_user_by_id
from ..models import User, SafetyRecord, MovementActivity
from ..agents.coordinator import agent_coordinator
from ..config import settings

router = APIRouter()
security = HTTPBearer()
logger = logging.getLogger(__name__)

@router.post("/data", status_code=status.HTTP_201_CREATED)
async def ingest_safety_data(
    data: Dict[str, Any],
    user_id: int = Query(..., description="User ID"),
    db: AsyncSession = Depends(get_db)
):
    """Ingest safety monitoring data from wearable devices and sensors"""
    try:
        # Validate user exists
        user = await get_user_by_id(user_id, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )

        # Process data through safety agent
        await agent_coordinator.process_safety_data(user_id, data)

        return {
            "message": "Safety data processed successfully",
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error ingesting safety data: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process safety data"
        )

@router.get("/records/{user_id}")
async def get_safety_records(
    user_id: int,
    limit: int = Query(50, description="Number of records to retrieve", ge=1, le=1000),
    hours: Optional[int] = Query(None, description="Get records from last N hours"),
    db: AsyncSession = Depends(get_db)
):
    """Get safety monitoring records for a user"""
    try:
        # Validate user exists
        user = await get_user_by_id(user_id, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )

        # Get records
        records = await get_recent_safety_records(user_id, limit, db)

        # Filter by time if specified
        if hours:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)
            records = [r for r in records if r.timestamp >= cutoff_time]

        # Convert to response format
        response_data = []
        for record in records:
            response_data.append({
                "id": record.id,
                "user_id": record.user_id,
                "timestamp": record.timestamp.isoformat(),
                "movement_activity": record.movement_activity.value if record.movement_activity else None,
                "acceleration_x": record.acceleration_x,
                "acceleration_y": record.acceleration_y,
                "acceleration_z": record.acceleration_z,
                "fall_detected": record.fall_detected,
                "impact_force": record.impact_force,
                "fall_confidence": record.fall_confidence,
                "post_fall_inactivity_duration": record.post_fall_inactivity_duration,
                "location_room": record.location_room,
                "location_coordinates": record.location_coordinates,
                "battery_level": record.battery_level,
                "safety_alert": record.safety_alert,
                "caregiver_notified": record.caregiver_notified,
                "device_type": record.device_type,
                "created_at": record.created_at.isoformat()
            })

        return {
            "user_id": user_id,
            "total_records": len(response_data),
            "records": response_data
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving safety records: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve safety records"
        )

@router.get("/status/{user_id}")
async def get_safety_status(user_id: int, db: AsyncSession = Depends(get_db)):
    """Get current safety status for a user"""
    try:
        # Validate user exists
        user = await get_user_by_id(user_id, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )

        # Get safety agent status
        if "safety" in agent_coordinator.agents:
            status_info = await agent_coordinator.agents["safety"].get_user_safety_status(user_id)
        else:
            status_info = {"error": "Safety agent not available"}

        return {
            "user_id": user_id,
            "safety_status": status_info,
            "timestamp": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving safety status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve safety status"
        )

@router.get("/falls/{user_id}")
async def get_fall_history(
    user_id: int,
    days: int = Query(30, description="Number of days to look back", ge=1, le=365),
    db: AsyncSession = Depends(get_db)
):
    """Get fall detection history for a user"""
    try:
        # Validate user exists
        user = await get_user_by_id(user_id, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )

        # Get safety records
        records = await get_recent_safety_records(user_id, limit=1000, session=db)

        # Filter for falls within time period
        cutoff_time = datetime.utcnow() - timedelta(days=days)
        fall_records = [
            r for r in records
            if r.timestamp >= cutoff_time and r.fall_detected
        ]

        # Convert to response format
        falls = []
        for record in fall_records:
            falls.append({
                "id": record.id,
                "timestamp": record.timestamp.isoformat(),
                "confidence": record.fall_confidence,
                "impact_force": record.impact_force,
                "location_room": record.location_room,
                "location_coordinates": record.location_coordinates,
                "post_fall_inactivity_duration": record.post_fall_inactivity_duration,
                "caregiver_notified": record.caregiver_notified,
                "device_type": record.device_type
            })

        return {
            "user_id": user_id,
            "time_period_days": days,
            "total_falls": len(falls),
            "falls": falls
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving fall history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve fall history"
        )

@router.get("/alerts/{user_id}")
async def get_safety_alerts(
    user_id: int,
    hours: int = Query(24, description="Time period in hours", ge=1, le=168),
    db: AsyncSession = Depends(get_db)
):
    """Get safety alerts for a user"""
    try:
        # Validate user exists
        user = await get_user_by_id(user_id, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )

        # Get safety records with alerts
        records = await get_recent_safety_records(user_id, limit=1000, session=db)

        # Filter by time and alert status
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        alert_records = [
            r for r in records
            if r.timestamp >= cutoff_time and r.safety_alert
        ]

        # Convert to response format
        alerts = []
        for record in alert_records:
            alert_info = {
                "record_id": record.id,
                "timestamp": record.timestamp.isoformat(),
                "alert_type": "fall" if record.fall_detected else "inactivity",
                "details": {}
            }

            if record.fall_detected:
                alert_info["details"] = {
                    "fall_confidence": record.fall_confidence,
                    "impact_force": record.impact_force,
                    "location": record.location_room,
                    "post_fall_inactivity": record.post_fall_inactivity_duration
                }
            else:
                # Inactivity alert
                alert_info["details"] = {
                    "inactivity_duration": record.post_fall_inactivity_duration,
                    "location": record.location_room
                }

            alerts.append(alert_info)

        return {
            "user_id": user_id,
            "time_period_hours": hours,
            "total_alerts": len(alerts),
            "alerts": alerts
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving safety alerts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve safety alerts"
        )

@router.get("/movement/{user_id}")
async def get_movement_analysis(
    user_id: int,
    hours: int = Query(24, description="Time period in hours for analysis", ge=1, le=168),
    db: AsyncSession = Depends(get_db)
):
    """Get movement pattern analysis for a user"""
    try:
        # Validate user exists
        user = await get_user_by_id(user_id, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )

        # Get safety records
        records = await get_recent_safety_records(user_id, limit=1000, session=db)

        # Filter by time period
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        recent_records = [r for r in records if r.timestamp >= cutoff_time]

        if not recent_records:
            return {
                "user_id": user_id,
                "time_period_hours": hours,
                "message": "No safety records found for the specified period",
                "analysis": {}
            }

        # Analyze movement patterns
        analysis = await _analyze_movement_patterns(recent_records)

        return {
            "user_id": user_id,
            "time_period_hours": hours,
            "total_records": len(recent_records),
            "analysis": analysis
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing movement patterns: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to analyze movement patterns"
        )

@router.get("/settings")
async def get_safety_settings():
    """Get safety monitoring settings and thresholds"""
    return {
        "fall_detection": {
            "enabled": True,
            "sensitivity": settings.fall_detection_sensitivity,
            "acceleration_threshold": 2.5,
            "impact_force_threshold": 5.0
        },
        "inactivity_monitoring": {
            "enabled": True,
            "threshold_minutes": settings.inactivity_threshold_minutes,
            "check_interval_seconds": settings.movement_check_interval_seconds
        },
        "movement_activities": [activity.value for activity in MovementActivity],
        "emergency_response": {
            "critical_alert_priority": "critical",
            "emergency_notification_timeout": 300  # seconds
        }
    }

async def _analyze_movement_patterns(records: List[SafetyRecord]) -> Dict[str, Any]:
    """Analyze movement patterns from safety records"""
    if not records:
        return {}

    # Count activities
    activity_counts = {}
    for record in records:
        activity = record.movement_activity.value if record.movement_activity else "unknown"
        activity_counts[activity] = activity_counts.get(activity, 0) + 1

    # Calculate activity percentages
    total_records = len(records)
    activity_percentages = {
        activity: round((count / total_records) * 100, 1)
        for activity, count in activity_counts.items()
    }

    # Analyze location patterns
    location_counts = {}
    for record in records:
        location = record.location_room or "unknown"
        location_counts[location] = location_counts.get(location, 0) + 1

    # Find most common locations
    sorted_locations = sorted(location_counts.items(), key=lambda x: x[1], reverse=True)
    top_locations = sorted_locations[:5]  # Top 5 locations

    # Analyze fall patterns
    fall_records = [r for r in records if r.fall_detected]
    fall_analysis = {
        "total_falls": len(fall_records),
        "fall_rate": round((len(fall_records) / total_records) * 100, 2) if total_records > 0 else 0,
        "average_confidence": round(sum(r.fall_confidence for r in fall_records) / len(fall_records), 2) if fall_records else 0
    }

    # Analyze time patterns
    hourly_activity = {}
    for record in records:
        hour = record.timestamp.hour
        activity = record.movement_activity.value if record.movement_activity else "unknown"
        if hour not in hourly_activity:
            hourly_activity[hour] = {}
        hourly_activity[hour][activity] = hourly_activity[hour].get(activity, 0) + 1

    # Find peak activity hours
    peak_hour = max(hourly_activity.keys(), key=lambda h: sum(hourly_activity[h].values())) if hourly_activity else None

    return {
        "activity_distribution": activity_percentages,
        "top_locations": [{"location": loc, "count": count} for loc, count in top_locations],
        "fall_analysis": fall_analysis,
        "peak_activity_hour": peak_hour,
        "hourly_patterns": hourly_activity,
        "total_alerts": sum(1 for r in records if r.safety_alert),
        "caregiver_notifications": sum(1 for r in records if r.caregiver_notified)
    }
