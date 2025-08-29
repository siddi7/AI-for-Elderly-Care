# Health Monitoring Agent for Elderly Care AI System

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from ..config import settings
from ..database import get_db, create_health_record, get_user_by_id, get_recent_health_records
from ..models import Alert, AlertPriority, AlertType, User
from ..websocket_manager import websocket_manager

logger = logging.getLogger(__name__)

class HealthMonitoringAgent:
    """AI agent for monitoring and analyzing health data"""

    def __init__(self):
        self.is_running = False
        self.ml_model = None
        self.scaler = StandardScaler()
        self.baseline_data = {}  # Store baseline health data per user

    async def start(self):
        """Start the health monitoring agent"""
        logger.info("Starting Health Monitoring Agent...")
        self.is_running = True

        # Initialize ML model for anomaly detection
        if settings.prediction_enabled:
            self._initialize_ml_model()

        # Load baseline data for existing users
        await self._load_baseline_data()

        logger.info("Health Monitoring Agent started successfully")

    async def stop(self):
        """Stop the health monitoring agent"""
        logger.info("Stopping Health Monitoring Agent...")
        self.is_running = False
        logger.info("Health Monitoring Agent stopped")

    async def health_check(self) -> Dict[str, Any]:
        """Health check for the agent"""
        return {
            "healthy": self.is_running,
            "ml_model_loaded": self.ml_model is not None,
            "baseline_users": len(self.baseline_data)
        }

    async def get_status(self) -> Dict[str, Any]:
        """Get agent status"""
        return {
            "name": "Health Monitoring Agent",
            "status": "running" if self.is_running else "stopped",
            "ml_enabled": settings.prediction_enabled,
            "model_trained": self.ml_model is not None,
            "monitored_users": len(self.baseline_data)
        }

    async def process_data(self, user_id: int, data: Dict[str, Any]):
        """Process incoming health data"""
        try:
            async with get_db() as session:
                # Get user information
                user = await get_user_by_id(user_id, session)
                if not user:
                    logger.warning(f"User {user_id} not found")
                    return

                # Validate and clean data
                cleaned_data = self._validate_health_data(data)

                # Analyze health data
                analysis_result = await self._analyze_health_data(user_id, cleaned_data, user)

                # Create health record
                record_data = {
                    "user_id": user_id,
                    "timestamp": data.get("timestamp", datetime.utcnow()),
                    **cleaned_data,
                    **analysis_result
                }

                record = await create_health_record(record_data, session)

                # Send real-time updates
                await self._send_realtime_update(user_id, record_data, analysis_result)

                # Handle alerts if any
                if analysis_result["alert_triggered"]:
                    await self._create_health_alert(user_id, analysis_result, session)

                logger.info(f"Processed health data for user {user_id}")

        except Exception as e:
            logger.error(f"Error processing health data for user {user_id}: {e}")

    def _validate_health_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and clean incoming health data"""
        validated_data = {}

        # Heart rate validation
        if "heart_rate" in data:
            hr = data["heart_rate"]
            if isinstance(hr, (int, float)) and 30 <= hr <= 200:
                validated_data["heart_rate"] = int(hr)
                validated_data["heart_rate_alert"] = (
                    hr < settings.heart_rate_min or hr > settings.heart_rate_max
                )

        # Blood pressure validation
        if "blood_pressure_systolic" in data and "blood_pressure_diastolic" in data:
            systolic = data["blood_pressure_systolic"]
            diastolic = data["blood_pressure_diastolic"]

            if (isinstance(systolic, (int, float)) and isinstance(diastolic, (int, float)) and
                70 <= systolic <= 250 and 40 <= diastolic <= 150 and systolic > diastolic):

                validated_data["blood_pressure_systolic"] = int(systolic)
                validated_data["blood_pressure_diastolic"] = int(diastolic)
                validated_data["blood_pressure_alert"] = (
                    systolic > settings.blood_pressure_systolic_max or
                    diastolic > settings.blood_pressure_diastolic_max or
                    systolic < settings.blood_pressure_systolic_min or
                    diastolic < settings.blood_pressure_diastolic_min
                )

        # Glucose level validation
        if "glucose_level" in data:
            glucose = data["glucose_level"]
            if isinstance(glucose, (int, float)) and 20 <= glucose <= 600:
                validated_data["glucose_level"] = float(glucose)
                validated_data["glucose_alert"] = (
                    glucose < settings.glucose_min or glucose > settings.glucose_max
                )

        # Oxygen saturation validation
        if "oxygen_saturation" in data:
            spo2 = data["oxygen_saturation"]
            if isinstance(spo2, (int, float)) and 70 <= spo2 <= 100:
                validated_data["oxygen_saturation"] = float(spo2)
                validated_data["oxygen_saturation_alert"] = spo2 < settings.oxygen_saturation_min

        # Additional metrics
        if "temperature" in data:
            temp = data["temperature"]
            if isinstance(temp, (int, float)) and 30 <= temp <= 45:
                validated_data["temperature"] = float(temp)

        if "respiratory_rate" in data:
            rr = data["respiratory_rate"]
            if isinstance(rr, (int, float)) and 5 <= rr <= 60:
                validated_data["respiratory_rate"] = int(rr)

        return validated_data

    async def _analyze_health_data(self, user_id: int, data: Dict[str, Any], user: User) -> Dict[str, Any]:
        """Analyze health data for anomalies and trends"""
        analysis = {
            "alert_triggered": False,
            "alert_reasons": [],
            "risk_level": "low",
            "recommendations": []
        }

        # Check for immediate alerts
        alert_flags = [
            data.get("heart_rate_alert", False),
            data.get("blood_pressure_alert", False),
            data.get("glucose_alert", False),
            data.get("oxygen_saturation_alert", False)
        ]

        if any(alert_flags):
            analysis["alert_triggered"] = True
            analysis["risk_level"] = "high"

            # Determine specific alert reasons
            if data.get("heart_rate_alert"):
                hr = data.get("heart_rate")
                if hr < settings.heart_rate_min:
                    analysis["alert_reasons"].append(f"Low heart rate: {hr} bpm")
                    analysis["recommendations"].append("Seek medical attention for bradycardia")
                elif hr > settings.heart_rate_max:
                    analysis["alert_reasons"].append(f"High heart rate: {hr} bpm")
                    analysis["recommendations"].append("Monitor for tachycardia symptoms")

            if data.get("blood_pressure_alert"):
                systolic = data.get("blood_pressure_systolic")
                diastolic = data.get("blood_pressure_diastolic")
                analysis["alert_reasons"].append(f"Blood pressure: {systolic}/{diastolic} mmHg")
                analysis["recommendations"].append("Consult healthcare provider about blood pressure")

            if data.get("glucose_alert"):
                glucose = data.get("glucose_level")
                if glucose < settings.glucose_min:
                    analysis["alert_reasons"].append(f"Low glucose: {glucose} mg/dL")
                    analysis["recommendations"].append("Check blood sugar and consume carbohydrates if needed")
                elif glucose > settings.glucose_max:
                    analysis["alert_reasons"].append(f"High glucose: {glucose} mg/dL")
                    analysis["recommendations"].append("Monitor blood sugar and consult healthcare provider")

            if data.get("oxygen_saturation_alert"):
                spo2 = data.get("oxygen_saturation")
                analysis["alert_reasons"].append(f"Low oxygen saturation: {spo2}%")
                analysis["recommendations"].append("Seek immediate medical attention for low oxygen levels")

        # ML-based anomaly detection
        if settings.prediction_enabled and self.ml_model and user_id in self.baseline_data:
            anomaly_score = self._detect_anomaly(user_id, data)
            if anomaly_score > 0.7:  # High anomaly score
                analysis["alert_triggered"] = True
                analysis["risk_level"] = "high"
                analysis["alert_reasons"].append("Unusual health pattern detected")
                analysis["recommendations"].append("Schedule consultation with healthcare provider")

        # Overall health assessment
        if not analysis["alert_triggered"]:
            analysis["risk_level"] = "low"
            analysis["recommendations"].append("Health metrics within normal ranges")

        return analysis

    def _detect_anomaly(self, user_id: int, data: Dict[str, Any]) -> float:
        """Detect anomalies using ML model"""
        try:
            # Prepare features for ML model
            features = self._extract_features(data)

            if not features:
                return 0.0

            # Scale features
            features_scaled = self.scaler.transform([features])

            # Predict anomaly score
            anomaly_score = self.ml_model.decision_function(features_scaled)[0]

            # Convert to 0-1 scale (higher = more anomalous)
            return 1 / (1 + np.exp(anomaly_score))  # Sigmoid transformation

        except Exception as e:
            logger.error(f"ML anomaly detection error: {e}")
            return 0.0

    def _extract_features(self, data: Dict[str, Any]) -> List[float]:
        """Extract features for ML model"""
        features = []

        # Vital signs
        features.append(data.get("heart_rate", 0))
        features.append(data.get("blood_pressure_systolic", 0))
        features.append(data.get("blood_pressure_diastolic", 0))
        features.append(data.get("glucose_level", 0))
        features.append(data.get("oxygen_saturation", 0))
        features.append(data.get("temperature", 0))
        features.append(data.get("respiratory_rate", 0))

        return features

    def _initialize_ml_model(self):
        """Initialize ML model for anomaly detection"""
        try:
            self.ml_model = IsolationForest(
                n_estimators=100,
                contamination=0.1,
                random_state=42
            )
            logger.info("ML model initialized for anomaly detection")
        except Exception as e:
            logger.error(f"Failed to initialize ML model: {e}")
            self.ml_model = None

    async def _load_baseline_data(self):
        """Load baseline health data for existing users"""
        try:
            async with get_db() as session:
                from sqlalchemy import select
                from ..models import User

                result = await session.execute(
                    select(User).where(User.is_active == True)
                )
                users = result.scalars().all()

                for user in users:
                    health_records = await get_recent_health_records(user.id, limit=100, session=session)
                    if len(health_records) >= 20:  # Need minimum data for baseline
                        self.baseline_data[user.id] = health_records
                        logger.info(f"Loaded baseline data for user {user.id}")

                # Train ML model if we have sufficient data
                if self.baseline_data and settings.prediction_enabled:
                    await self._train_ml_model()

        except Exception as e:
            logger.error(f"Failed to load baseline data: {e}")

    async def _train_ml_model(self):
        """Train ML model on baseline data"""
        try:
            all_features = []

            for user_id, records in self.baseline_data.items():
                for record in records[-50:]:  # Use last 50 records for training
                    features = self._extract_features({
                        "heart_rate": record.heart_rate,
                        "blood_pressure_systolic": record.blood_pressure_systolic,
                        "blood_pressure_diastolic": record.blood_pressure_diastolic,
                        "glucose_level": record.glucose_level,
                        "oxygen_saturation": record.oxygen_saturation,
                        "temperature": record.temperature,
                        "respiratory_rate": record.respiratory_rate
                    })

                    if all(f != 0 for f in features):  # Only include complete records
                        all_features.append(features)

            if len(all_features) >= 100:  # Need minimum training data
                # Fit scaler
                self.scaler.fit(all_features)

                # Scale features
                features_scaled = self.scaler.transform(all_features)

                # Train model
                self.ml_model.fit(features_scaled)
                logger.info(f"ML model trained on {len(all_features)} samples")

        except Exception as e:
            logger.error(f"Failed to train ML model: {e}")

    async def _send_realtime_update(self, user_id: int, data: Dict[str, Any], analysis: Dict[str, Any]):
        """Send real-time health updates via WebSocket"""
        try:
            update_data = {
                "type": "health_update",
                "user_id": user_id,
                "timestamp": datetime.utcnow().isoformat(),
                "vitals": {
                    "heart_rate": data.get("heart_rate"),
                    "blood_pressure": f"{data.get('blood_pressure_systolic')}/{data.get('blood_pressure_diastolic')}",
                    "glucose": data.get("glucose_level"),
                    "oxygen_saturation": data.get("oxygen_saturation")
                },
                "analysis": {
                    "risk_level": analysis["risk_level"],
                    "alert_triggered": analysis["alert_triggered"]
                }
            }

            await websocket_manager.broadcast_to_user(user_id, update_data)

        except Exception as e:
            logger.error(f"Failed to send real-time update: {e}")

    async def _create_health_alert(self, user_id: int, analysis: Dict[str, Any], session):
        """Create health alert in database"""
        try:
            alert = Alert(
                user_id=user_id,
                alert_type=AlertType.HEALTH,
                priority=AlertPriority.HIGH if analysis["risk_level"] == "high" else AlertPriority.MEDIUM,
                title="Health Alert",
                message=f"Health monitoring alert: {', '.join(analysis['alert_reasons'])}",
                related_record_id=None  # Would link to specific health record
            )

            session.add(alert)
            await session.commit()

            # Notify caregivers
            await self._notify_caregivers(user_id, alert, session)

        except Exception as e:
            logger.error(f"Failed to create health alert: {e}")

    async def _notify_caregivers(self, user_id: int, alert: Alert, session):
        """Notify caregivers about health alerts"""
        try:
            # This would integrate with notification service
            # For now, just log the notification
            logger.info(f"Health alert notification for user {user_id}: {alert.message}")

            # TODO: Implement actual notification sending (SMS, email, push)

        except Exception as e:
            logger.error(f"Failed to notify caregivers: {e}")
