# Database Models for Elderly Care AI System

from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, Float, Text,
    ForeignKey, Enum, JSON, BigInteger
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

Base = declarative_base()

# Enums
class UserRole(str, enum.Enum):
    ELDERLY = "elderly"
    CAREGIVER = "caregiver"
    HEALTHCARE_PROVIDER = "healthcare_provider"
    ADMIN = "admin"

class AlertPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class AlertType(str, enum.Enum):
    HEALTH = "health"
    SAFETY = "safety"
    REMINDER = "reminder"
    SYSTEM = "system"

class ReminderType(str, enum.Enum):
    MEDICATION = "medication"
    APPOINTMENT = "appointment"
    EXERCISE = "exercise"
    HYDRATION = "hydration"
    MEAL = "meal"
    SOCIAL_ACTIVITY = "social_activity"
    OTHER = "other"

class MovementActivity(str, enum.Enum):
    WALKING = "walking"
    RUNNING = "running"
    LYING = "lying"
    SITTING = "sitting"
    STANDING = "standing"
    NO_MOVEMENT = "no_movement"

# User Management Models
class User(Base):
    """User model for elderly individuals, caregivers, and healthcare providers"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(50), unique=True, index=True)
    email = Column(String(255), unique=True, index=True)
    phone = Column(String(20))
    full_name = Column(String(255))
    role = Column(Enum(UserRole), nullable=False)
    is_active = Column(Boolean, default=True)
    emergency_contact = Column(String(20))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    health_records = relationship("HealthRecord", back_populates="user")
    safety_records = relationship("SafetyRecord", back_populates="user")
    reminders = relationship("Reminder", back_populates="user")
    alerts = relationship("Alert", back_populates="user")

    # Profile information
    date_of_birth = Column(DateTime)
    address = Column(Text)
    medical_conditions = Column(JSON)  # List of medical conditions
    allergies = Column(JSON)  # List of allergies
    medications = Column(JSON)  # Current medications
    emergency_contacts = Column(JSON)  # Additional emergency contacts

class CaregiverElderlyMapping(Base):
    """Mapping between caregivers and elderly individuals they care for"""
    __tablename__ = "caregiver_elderly_mapping"

    id = Column(Integer, primary_key=True)
    caregiver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    elderly_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    relationship_type = Column(String(100))  # family, professional, etc.
    notification_preferences = Column(JSON)
    is_primary_caregiver = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

# Health Monitoring Models
class HealthRecord(Base):
    """Health monitoring data from wearable devices"""
    __tablename__ = "health_records"

    id = Column(BigInteger, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)

    # Vital signs
    heart_rate = Column(Integer)
    heart_rate_alert = Column(Boolean, default=False)

    blood_pressure_systolic = Column(Integer)
    blood_pressure_diastolic = Column(Integer)
    blood_pressure_alert = Column(Boolean, default=False)

    glucose_level = Column(Float)
    glucose_alert = Column(Boolean, default=False)

    oxygen_saturation = Column(Float)
    oxygen_saturation_alert = Column(Boolean, default=False)

    # Additional metrics
    temperature = Column(Float)
    respiratory_rate = Column(Integer)
    sleep_quality = Column(Float)

    # Device information
    device_type = Column(String(100))
    device_firmware = Column(String(50))

    # Alert flags
    overall_health_alert = Column(Boolean, default=False)
    caregiver_notified = Column(Boolean, default=False)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime)

    # Relationships
    user = relationship("User", back_populates="health_records")

# Safety Monitoring Models
class SafetyRecord(Base):
    """Safety monitoring data including fall detection and movement tracking"""
    __tablename__ = "safety_records"

    id = Column(BigInteger, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)

    # Movement data
    movement_activity = Column(Enum(MovementActivity))
    acceleration_x = Column(Float)
    acceleration_y = Column(Float)
    acceleration_z = Column(Float)

    # Fall detection
    fall_detected = Column(Boolean, default=False)
    impact_force = Column(Float)
    fall_confidence = Column(Float)

    # Post-fall data
    post_fall_inactivity_duration = Column(Integer)  # seconds

    # Location data
    location_room = Column(String(100))
    location_coordinates = Column(String(100))  # GPS or indoor positioning

    # Device information
    device_type = Column(String(100))
    battery_level = Column(Float)

    # Alert flags
    safety_alert = Column(Boolean, default=False)
    caregiver_notified = Column(Boolean, default=False)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime)

    # Relationships
    user = relationship("User", back_populates="safety_records")

# Reminder Models
class Reminder(Base):
    """Medication and activity reminders"""
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reminder_type = Column(Enum(ReminderType), nullable=False)

    # Reminder details
    title = Column(String(255), nullable=False)
    description = Column(Text)
    scheduled_time = Column(DateTime, nullable=False, index=True)

    # Recurrence
    is_recurring = Column(Boolean, default=False)
    recurrence_pattern = Column(JSON)  # Cron-like pattern or custom rules

    # Status
    is_sent = Column(Boolean, default=False)
    is_acknowledged = Column(Boolean, default=False)
    acknowledged_at = Column(DateTime)

    # Voice reminder
    voice_message_url = Column(String(500))
    voice_enabled = Column(Boolean, default=True)

    # Escalation
    escalation_attempts = Column(Integer, default=0)
    max_escalation_attempts = Column(Integer, default=3)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="reminders")

# Alert Models
class Alert(Base):
    """System alerts for health, safety, and reminder issues"""
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    alert_type = Column(Enum(AlertType), nullable=False)
    priority = Column(Enum(AlertPriority), nullable=False, default=AlertPriority.MEDIUM)

    # Alert details
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    related_record_id = Column(BigInteger)  # ID of related health/safety/reminder record

    # Notification channels
    email_sent = Column(Boolean, default=False)
    sms_sent = Column(Boolean, default=False)
    push_sent = Column(Boolean, default=False)
    voice_call_made = Column(Boolean, default=False)

    # Escalation
    escalation_level = Column(Integer, default=0)
    max_escalation_level = Column(Integer, default=3)

    # Resolution
    is_resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime)
    resolved_by = Column(Integer, ForeignKey("users.id"))
    resolution_notes = Column(Text)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="alerts")

# System Configuration Models
class SystemConfiguration(Base):
    """System-wide configuration settings"""
    __tablename__ = "system_configuration"

    id = Column(Integer, primary_key=True)
    key = Column(String(255), unique=True, nullable=False)
    value = Column(JSON)
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# ML Model Performance Tracking
class MLModelPerformance(Base):
    """Track performance of ML models used in the system"""
    __tablename__ = "ml_model_performance"

    id = Column(Integer, primary_key=True)
    model_name = Column(String(255), nullable=False)
    model_version = Column(String(50))
    metric_name = Column(String(100), nullable=False)
    metric_value = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

    # Metadata
    dataset_size = Column(Integer)
    training_time = Column(Float)  # seconds
    prediction_accuracy = Column(Float)
