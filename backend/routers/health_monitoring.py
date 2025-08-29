# Health Monitoring API Router

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.security import HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging

from ..database import get_db, create_health_record, get_recent_health_records, get_user_by_id
from ..models import User, HealthRecord
from ..agents.coordinator import agent_coordinator
from ..config import settings

router = APIRouter()
security = HTTPBearer()
logger = logging.getLogger(__name__)

@router.post("/data", status_code=status.HTTP_201_CREATED)
async def ingest_health_data(
    data: Dict[str, Any],
    user_id: int = Query(..., description="User ID"),
    db: AsyncSession = Depends(get_db)
):
    """Ingest health monitoring data from wearable devices"""
    try:
        # Validate user exists
        user = await get_user_by_id(user_id, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )

        # Process data through health agent
        await agent_coordinator.process_health_data(user_id, data)

        return {
            "message": "Health data processed successfully",
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error ingesting health data: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process health data"
        )

@router.get("/records/{user_id}")
async def get_health_records(
    user_id: int,
    limit: int = Query(50, description="Number of records to retrieve", ge=1, le=1000),
    hours: Optional[int] = Query(None, description="Get records from last N hours"),
    db: AsyncSession = Depends(get_db)
):
    """Get health monitoring records for a user"""
    try:
        # Validate user exists
        user = await get_user_by_id(user_id, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )

        # Get records
        records = await get_recent_health_records(user_id, limit, db)

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
                "heart_rate": record.heart_rate,
                "blood_pressure_systolic": record.blood_pressure_systolic,
                "blood_pressure_diastolic": record.blood_pressure_diastolic,
                "glucose_level": record.glucose_level,
                "oxygen_saturation": record.oxygen_saturation,
                "temperature": record.temperature,
                "respiratory_rate": record.respiratory_rate,
                "heart_rate_alert": record.heart_rate_alert,
                "blood_pressure_alert": record.blood_pressure_alert,
                "glucose_alert": record.glucose_alert,
                "oxygen_saturation_alert": record.oxygen_saturation_alert,
                "overall_health_alert": record.overall_health_alert,
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
        logger.error(f"Error retrieving health records: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve health records"
        )

@router.get("/summary/{user_id}")
async def get_health_summary(
    user_id: int,
    hours: int = Query(24, description="Time period in hours for summary", ge=1, le=168),
    db: AsyncSession = Depends(get_db)
):
    """Get health summary and trends for a user"""
    try:
        # Validate user exists
        user = await get_user_by_id(user_id, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )

        # Get recent records
        records = await get_recent_health_records(user_id, limit=1000, session=db)

        # Filter by time period
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        recent_records = [r for r in records if r.timestamp >= cutoff_time]

        if not recent_records:
            return {
                "user_id": user_id,
                "time_period_hours": hours,
                "message": "No health records found for the specified period",
                "summary": {}
            }

        # Calculate summary statistics
        summary = await _calculate_health_summary(recent_records)

        # Get current health status
        latest_record = max(recent_records, key=lambda r: r.timestamp)
        current_status = {
            "timestamp": latest_record.timestamp.isoformat(),
            "heart_rate": latest_record.heart_rate,
            "blood_pressure": f"{latest_record.blood_pressure_systolic}/{latest_record.blood_pressure_diastolic}",
            "glucose_level": latest_record.glucose_level,
            "oxygen_saturation": latest_record.oxygen_saturation,
            "overall_status": "normal" if not latest_record.overall_health_alert else "alert"
        }

        return {
            "user_id": user_id,
            "time_period_hours": hours,
            "total_records": len(recent_records),
            "current_status": current_status,
            "summary": summary
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating health summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate health summary"
        )

@router.get("/alerts/{user_id}")
async def get_health_alerts(
    user_id: int,
    hours: int = Query(24, description="Time period in hours", ge=1, le=168),
    resolved: bool = Query(False, description="Include resolved alerts"),
    db: AsyncSession = Depends(get_db)
):
    """Get health alerts for a user"""
    try:
        # Validate user exists
        user = await get_user_by_id(user_id, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )

        # Get health records with alerts
        records = await get_recent_health_records(user_id, limit=1000, session=db)

        # Filter by time and alert status
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        alert_records = []

        for record in records:
            if record.timestamp >= cutoff_time:
                if record.overall_health_alert or record.heart_rate_alert or \
                   record.blood_pressure_alert or record.glucose_alert or \
                   record.oxygen_saturation_alert:
                    alert_records.append(record)

        # Convert to response format
        alerts = []
        for record in alert_records:
            alert_info = {
                "record_id": record.id,
                "timestamp": record.timestamp.isoformat(),
                "alerts": []
            }

            if record.heart_rate_alert:
                alert_info["alerts"].append({
                    "type": "heart_rate",
                    "value": record.heart_rate,
                    "threshold": f"{settings.heart_rate_min}-{settings.heart_rate_max} bpm"
                })

            if record.blood_pressure_alert:
                alert_info["alerts"].append({
                    "type": "blood_pressure",
                    "value": f"{record.blood_pressure_systolic}/{record.blood_pressure_diastolic}",
                    "threshold": f"{settings.blood_pressure_systolic_min}-{settings.blood_pressure_systolic_max}/{settings.blood_pressure_diastolic_min}-{settings.blood_pressure_diastolic_max} mmHg"
                })

            if record.glucose_alert:
                alert_info["alerts"].append({
                    "type": "glucose",
                    "value": record.glucose_level,
                    "threshold": f"{settings.glucose_min}-{settings.glucose_max} mg/dL"
                })

            if record.oxygen_saturation_alert:
                alert_info["alerts"].append({
                    "type": "oxygen_saturation",
                    "value": record.oxygen_saturation,
                    "threshold": f">{settings.oxygen_saturation_min}%"
                })

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
        logger.error(f"Error retrieving health alerts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve health alerts"
        )

@router.get("/thresholds")
async def get_health_thresholds():
    """Get health monitoring thresholds"""
    return {
        "heart_rate": {
            "min": settings.heart_rate_min,
            "max": settings.heart_rate_max,
            "unit": "bpm"
        },
        "blood_pressure": {
            "systolic_min": settings.blood_pressure_systolic_min,
            "systolic_max": settings.blood_pressure_systolic_max,
            "diastolic_min": settings.blood_pressure_diastolic_min,
            "diastolic_max": settings.blood_pressure_diastolic_max,
            "unit": "mmHg"
        },
        "glucose": {
            "min": settings.glucose_min,
            "max": settings.glucose_max,
            "unit": "mg/dL"
        },
        "oxygen_saturation": {
            "min": settings.oxygen_saturation_min,
            "unit": "%"
        }
    }

async def _calculate_health_summary(records: List[HealthRecord]) -> Dict[str, Any]:
    """Calculate health summary statistics"""
    if not records:
        return {}

    # Extract values
    heart_rates = [r.heart_rate for r in records if r.heart_rate]
    systolic_bp = [r.blood_pressure_systolic for r in records if r.blood_pressure_systolic]
    diastolic_bp = [r.blood_pressure_diastolic for r in records if r.blood_pressure_diastolic]
    glucose_levels = [r.glucose_level for r in records if r.glucose_level]
    oxygen_levels = [r.oxygen_saturation for r in records if r.oxygen_saturation]

    summary = {
        "total_records": len(records),
        "date_range": {
            "start": min(r.timestamp for r in records).isoformat(),
            "end": max(r.timestamp for r in records).isoformat()
        }
    }

    # Heart rate statistics
    if heart_rates:
        summary["heart_rate"] = {
            "average": round(sum(heart_rates) / len(heart_rates), 1),
            "min": min(heart_rates),
            "max": max(heart_rates),
            "alerts": sum(1 for r in records if r.heart_rate_alert)
        }

    # Blood pressure statistics
    if systolic_bp and diastolic_bp:
        summary["blood_pressure"] = {
            "average_systolic": round(sum(systolic_bp) / len(systolic_bp), 1),
            "average_diastolic": round(sum(diastolic_bp) / len(diastolic_bp), 1),
            "alerts": sum(1 for r in records if r.blood_pressure_alert)
        }

    # Glucose statistics
    if glucose_levels:
        summary["glucose"] = {
            "average": round(sum(glucose_levels) / len(glucose_levels), 1),
            "min": min(glucose_levels),
            "max": max(glucose_levels),
            "alerts": sum(1 for r in records if r.glucose_alert)
        }

    # Oxygen saturation statistics
    if oxygen_levels:
        summary["oxygen_saturation"] = {
            "average": round(sum(oxygen_levels) / len(oxygen_levels), 1),
            "min": min(oxygen_levels),
            "max": max(oxygen_levels),
            "alerts": sum(1 for r in records if r.oxygen_saturation_alert)
        }

    # Overall statistics
    summary["overall"] = {
        "total_alerts": sum(1 for r in records if r.overall_health_alert),
        "caregiver_notifications": sum(1 for r in records if r.caregiver_notified)
    }

    return summary
