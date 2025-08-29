# Safety Monitoring Agent for Elderly Care AI System

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import math

from ..config import settings
from ..database import get_db, create_safety_record, get_user_by_id, get_recent_safety_records
from ..models import Alert, AlertPriority, AlertType, MovementActivity
from ..websocket_manager import websocket_manager

logger = logging.getLogger(__name__)

class SafetyMonitoringAgent:
    """AI agent for monitoring safety and detecting falls"""

    def __init__(self):
        self.is_running = False
        self.fall_detection_model = None
        self.user_states = {}  # Track user movement states

    async def start(self):
        """Start the safety monitoring agent"""
        logger.info("Starting Safety Monitoring Agent...")
        self.is_running = True

        # Initialize fall detection model
        self._initialize_fall_detection()

        logger.info("Safety Monitoring Agent started successfully")

    async def stop(self):
        """Stop the safety monitoring agent"""
        logger.info("Stopping Safety Monitoring Agent...")
        self.is_running = False
        logger.info("Safety Monitoring Agent stopped")

    async def health_check(self) -> Dict[str, Any]:
        """Health check for the agent"""
        return {
            "healthy": self.is_running,
            "fall_detection_active": self.fall_detection_model is not None,
            "tracked_users": len(self.user_states)
        }

    async def get_status(self) -> Dict[str, Any]:
        """Get agent status"""
        return {
            "name": "Safety Monitoring Agent",
            "status": "running" if self.is_running else "stopped",
            "fall_detection_enabled": True,
            "active_users": len(self.user_states)
        }

    async def process_data(self, user_id: int, data: Dict[str, Any]):
        """Process incoming safety data"""
        try:
            async with get_db() as session:
                # Get user information
                user = await get_user_by_id(user_id, session)
                if not user:
                    logger.warning(f"User {user_id} not found")
                    return

                # Validate and clean data
                cleaned_data = self._validate_safety_data(data)

                # Analyze safety data
                analysis_result = await self._analyze_safety_data(user_id, cleaned_data, user)

                # Update user state
                self._update_user_state(user_id, cleaned_data, analysis_result)

                # Create safety record
                record_data = {
                    "user_id": user_id,
                    "timestamp": data.get("timestamp", datetime.utcnow()),
                    **cleaned_data,
                    **analysis_result
                }

                record = await create_safety_record(record_data, session)

                # Send real-time updates
                await self._send_realtime_update(user_id, record_data, analysis_result)

                # Handle alerts if any
                if analysis_result["alert_triggered"]:
                    await self._create_safety_alert(user_id, analysis_result, session)

                logger.info(f"Processed safety data for user {user_id}")

        except Exception as e:
            logger.error(f"Error processing safety data for user {user_id}: {e}")

    def _validate_safety_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and clean incoming safety data"""
        validated_data = {}

        # Movement activity
        if "movement_activity" in data:
            activity = data["movement_activity"]
            if activity in [e.value for e in MovementActivity]:
                validated_data["movement_activity"] = MovementActivity(activity)

        # Accelerometer data
        if "acceleration_x" in data:
            validated_data["acceleration_x"] = float(data["acceleration_x"])
        if "acceleration_y" in data:
            validated_data["acceleration_y"] = float(data["acceleration_y"])
        if "acceleration_z" in data:
            validated_data["acceleration_z"] = float(data["acceleration_z"])

        # Fall detection data
        if "impact_force" in data:
            validated_data["impact_force"] = float(data["impact_force"])

        # Location data
        if "location_room" in data:
            validated_data["location_room"] = str(data["location_room"])

        # Device data
        if "battery_level" in data:
            validated_data["battery_level"] = float(data["battery_level"])

        return validated_data

    async def _analyze_safety_data(self, user_id: int, data: Dict[str, Any], user: User) -> Dict[str, Any]:
        """Analyze safety data for fall detection and unusual activity"""
        analysis = {
            "fall_detected": False,
            "fall_confidence": 0.0,
            "alert_triggered": False,
            "alert_reasons": [],
            "risk_level": "low",
            "recommendations": []
        }

        # Fall detection
        if self._detect_fall(data):
            analysis["fall_detected"] = True
            analysis["fall_confidence"] = self._calculate_fall_confidence(data)
            analysis["alert_triggered"] = True
            analysis["alert_reasons"].append("Fall detected")
            analysis["risk_level"] = "critical"
            analysis["recommendations"].extend([
                "Check on elderly person immediately",
                "Call emergency services if unresponsive",
                "Check for injuries"
            ])

        # Movement analysis
        movement_analysis = self._analyze_movement_pattern(user_id, data)
        if movement_analysis["unusual_activity"]:
            analysis["alert_triggered"] = True
            analysis["alert_reasons"].extend(movement_analysis["reasons"])
            if analysis["risk_level"] == "low":
                analysis["risk_level"] = "medium"

        # Inactivity monitoring
        inactivity_analysis = await self._check_inactivity(user_id, data)
        if inactivity_analysis["inactive_too_long"]:
            analysis["alert_triggered"] = True
            analysis["alert_reasons"].append(f"Inactive for {inactivity_analysis['inactive_duration']} seconds")
            analysis["risk_level"] = "high"
            analysis["recommendations"].append("Check if person needs assistance")

        return analysis

    def _detect_fall(self, data: Dict[str, Any]) -> bool:
        """Detect potential falls using accelerometer data"""
        if not all(key in data for key in ["acceleration_x", "acceleration_y", "acceleration_z"]):
            return False

        # Calculate resultant acceleration
        resultant_acc = math.sqrt(
            data["acceleration_x"]**2 +
            data["acceleration_y"]**2 +
            data["acceleration_z"]**2
        )

        # Simple fall detection based on impact force
        # In a real system, this would use more sophisticated ML models
        impact_force = data.get("impact_force", 0)

        # Threshold-based detection
        if resultant_acc > 2.5 or impact_force > 5.0:  # Free fall acceleration ~2.5g
            return True

        return False

    def _calculate_fall_confidence(self, data: Dict[str, Any]) -> float:
        """Calculate confidence score for fall detection"""
        confidence = 0.0

        # Acceleration-based confidence
        if all(key in data for key in ["acceleration_x", "acceleration_y", "acceleration_z"]):
            resultant_acc = math.sqrt(
                data["acceleration_x"]**2 +
                data["acceleration_y"]**2 +
                data["acceleration_z"]**2
            )
            confidence += min(resultant_acc / 3.0, 1.0) * 0.6

        # Impact force confidence
        impact_force = data.get("impact_force", 0)
        confidence += min(impact_force / 10.0, 1.0) * 0.4

        return min(confidence, 1.0)

    def _analyze_movement_pattern(self, user_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze movement patterns for unusual activity"""
        analysis = {
            "unusual_activity": False,
            "reasons": []
        }

        current_activity = data.get("movement_activity")
        user_state = self.user_states.get(user_id, {})

        # Check for sudden changes in activity
        previous_activity = user_state.get("last_activity")
        if previous_activity and current_activity != previous_activity:
            # Check if this is an unusual transition
            unusual_transitions = [
                (MovementActivity.WALKING, MovementActivity.NO_MOVEMENT),
                (MovementActivity.RUNNING, MovementActivity.NO_MOVEMENT),
                (MovementActivity.STANDING, MovementActivity.LYING)
            ]

            for from_activity, to_activity in unusual_transitions:
                if (previous_activity == from_activity and
                    current_activity == to_activity):
                    analysis["unusual_activity"] = True
                    analysis["reasons"].append(
                        f"Sudden change from {previous_activity.value} to {current_activity.value}"
                    )
                    break

        return analysis

    async def _check_inactivity(self, user_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """Check for prolonged inactivity"""
        analysis = {
            "inactive_too_long": False,
            "inactive_duration": 0
        }

        current_activity = data.get("movement_activity")
        user_state = self.user_states.get(user_id, {})

        if current_activity == MovementActivity.NO_MOVEMENT:
            last_movement = user_state.get("last_movement_time")
            if last_movement:
                inactive_duration = (datetime.utcnow() - last_movement).total_seconds()
                analysis["inactive_duration"] = inactive_duration

                if inactive_duration > settings.inactivity_threshold_minutes * 60:
                    analysis["inactive_too_long"] = True
        else:
            # Update last movement time
            self.user_states[user_id]["last_movement_time"] = datetime.utcnow()

        return analysis

    def _update_user_state(self, user_id: int, data: Dict[str, Any], analysis: Dict[str, Any]):
        """Update user state tracking"""
        if user_id not in self.user_states:
            self.user_states[user_id] = {}

        user_state = self.user_states[user_id]

        # Update activity history
        current_activity = data.get("movement_activity")
        if current_activity:
            user_state["last_activity"] = current_activity

        # Update location history
        location = data.get("location_room")
        if location:
            user_state["last_location"] = location

        # Update fall history
        if analysis["fall_detected"]:
            if "fall_history" not in user_state:
                user_state["fall_history"] = []
            user_state["fall_history"].append({
                "timestamp": datetime.utcnow(),
                "confidence": analysis["fall_confidence"]
            })

            # Keep only last 10 falls
            user_state["fall_history"] = user_state["fall_history"][-10:]

        # Update battery status
        battery_level = data.get("battery_level")
        if battery_level:
            user_state["battery_level"] = battery_level
            if battery_level < 20:
                user_state["low_battery_alert"] = True

    def _initialize_fall_detection(self):
        """Initialize fall detection model"""
        # In a real implementation, this would load a trained ML model
        # For now, we'll use simple threshold-based detection
        self.fall_detection_model = {
            "threshold_acceleration": 2.5,  # g
            "threshold_impact": 5.0,
            "sensitivity": settings.fall_detection_sensitivity
        }
        logger.info("Fall detection model initialized")

    async def _send_realtime_update(self, user_id: int, data: Dict[str, Any], analysis: Dict[str, Any]):
        """Send real-time safety updates via WebSocket"""
        try:
            update_data = {
                "type": "safety_update",
                "user_id": user_id,
                "timestamp": datetime.utcnow().isoformat(),
                "movement": {
                    "activity": data.get("movement_activity").value if data.get("movement_activity") else None,
                    "location": data.get("location_room"),
                    "acceleration": {
                        "x": data.get("acceleration_x"),
                        "y": data.get("acceleration_y"),
                        "z": data.get("acceleration_z")
                    }
                },
                "fall_detection": {
                    "detected": analysis["fall_detected"],
                    "confidence": analysis["fall_confidence"]
                },
                "analysis": {
                    "risk_level": analysis["risk_level"],
                    "alert_triggered": analysis["alert_triggered"]
                }
            }

            await websocket_manager.broadcast_to_user(user_id, update_data)

        except Exception as e:
            logger.error(f"Failed to send real-time safety update: {e}")

    async def _create_safety_alert(self, user_id: int, analysis: Dict[str, Any], session):
        """Create safety alert in database"""
        try:
            alert = Alert(
                user_id=user_id,
                alert_type=AlertType.SAFETY,
                priority=AlertPriority.CRITICAL if analysis["risk_level"] == "critical" else AlertPriority.HIGH,
                title="Safety Alert",
                message=f"Safety monitoring alert: {', '.join(analysis['alert_reasons'])}",
                related_record_id=None  # Would link to specific safety record
            )

            session.add(alert)
            await session.commit()

            # Notify caregivers immediately for critical alerts
            if analysis["risk_level"] == "critical":
                await self._notify_emergency_contacts(user_id, alert, session)
            else:
                await self._notify_caregivers(user_id, alert, session)

        except Exception as e:
            logger.error(f"Failed to create safety alert: {e}")

    async def _notify_caregivers(self, user_id: int, alert: Alert, session):
        """Notify caregivers about safety alerts"""
        try:
            # This would integrate with notification service
            logger.info(f"Safety alert notification for user {user_id}: {alert.message}")

            # TODO: Implement actual notification sending (SMS, email, push)

        except Exception as e:
            logger.error(f"Failed to notify caregivers: {e}")

    async def _notify_emergency_contacts(self, user_id: int, alert: Alert, session):
        """Notify emergency contacts for critical alerts"""
        try:
            # Get user information
            user = await get_user_by_id(user_id, session)
            if not user:
                return

            # Get emergency contacts
            emergency_contacts = user.emergency_contacts or []

            logger.critical(f"CRITICAL SAFETY ALERT for {user.full_name}: {alert.message}")

            # TODO: Implement emergency notification system
            # This should trigger immediate SMS, phone calls, and emergency services

            for contact in emergency_contacts:
                logger.critical(f"Notifying emergency contact: {contact}")

        except Exception as e:
            logger.error(f"Failed to notify emergency contacts: {e}")

    async def get_user_safety_status(self, user_id: int) -> Dict[str, Any]:
        """Get comprehensive safety status for a user"""
        user_state = self.user_states.get(user_id, {})

        # Get recent safety records
        async with get_db() as session:
            recent_records = await get_recent_safety_records(user_id, limit=10, session=session)

        status = {
            "user_id": user_id,
            "current_activity": user_state.get("last_activity"),
            "current_location": user_state.get("last_location"),
            "battery_level": user_state.get("battery_level"),
            "last_movement": user_state.get("last_movement_time"),
            "fall_history": user_state.get("fall_history", []),
            "recent_records": len(recent_records),
            "alerts_active": any(record.safety_alert for record in recent_records)
        }

        return status
