# Data Ingestion Script for Elderly Care AI System

import pandas as pd
import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Any
from pathlib import Path

from backend.database import get_db, create_health_record, create_safety_record
from backend.models import User, Reminder, ReminderType
from backend.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataIngestionService:
    """Service for ingesting data from CSV files into the database"""

    def __init__(self, data_directory: str = "data"):
        self.data_directory = Path(data_directory)
        self.ingested_users = set()

    async def ingest_all_data(self):
        """Ingest all available CSV data files"""
        logger.info("Starting data ingestion process...")

        try:
            # Ingest health monitoring data
            await self.ingest_health_monitoring_data()

            # Ingest safety monitoring data
            await self.ingest_safety_monitoring_data()

            # Ingest reminder data
            await self.ingest_reminder_data()

            # Create sample users if needed
            await self.create_sample_users()

            logger.info("Data ingestion completed successfully")

        except Exception as e:
            logger.error(f"Data ingestion failed: {e}")
            raise

    async def ingest_health_monitoring_data(self):
        """Ingest health monitoring data from CSV"""
        csv_file = self.data_directory / "health_monitoring.csv"

        if not csv_file.exists():
            logger.warning(f"Health monitoring CSV file not found: {csv_file}")
            return

        logger.info(f"Reading health monitoring data from {csv_file}")

        # Read CSV file
        df = pd.read_csv(csv_file)

        # Convert timestamp column
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], format='%m/%d/%Y %H:%M')

        async with get_db() as session:
            for _, row in df.iterrows():
                try:
                    # Extract user ID from Device-ID/User-ID column
                    user_id = self._extract_user_id(row['Device-ID/User-ID'])

                    # Check if user exists, create if not
                    await self._ensure_user_exists(user_id, session)

                    # Prepare health record data
                    record_data = {
                        "user_id": user_id,
                        "timestamp": row['Timestamp'].to_pydatetime(),
                        "heart_rate": row['Heart Rate'] if pd.notna(row['Heart Rate']) else None,
                        "blood_pressure_systolic": self._parse_blood_pressure(row['Blood Pressure'], 'systolic'),
                        "blood_pressure_diastolic": self._parse_blood_pressure(row['Blood Pressure'], 'diastolic'),
                        "glucose_level": row['Glucose Levels'] if pd.notna(row['Glucose Levels']) else None,
                        "oxygen_saturation": row['Oxygen Saturation (SpO₂%)'] if pd.notna(row['Oxygen Saturation (SpO₂%)']) else None,
                        "device_type": "wearable_device",
                        "overall_health_alert": row['Alert Triggered (Yes/No)'] == 'Yes',
                        "caregiver_notified": row['Caregiver Notified (Yes/No)'] == 'Yes'
                    }

                    # Create health record
                    await create_health_record(record_data, session)

                except Exception as e:
                    logger.error(f"Error processing health record: {e}")
                    continue

        logger.info(f"Ingested {len(df)} health monitoring records")

    async def ingest_safety_monitoring_data(self):
        """Ingest safety monitoring data from CSV"""
        csv_file = self.data_directory / "safety_monitoring.csv"

        if not csv_file.exists():
            logger.warning(f"Safety monitoring CSV file not found: {csv_file}")
            return

        logger.info(f"Reading safety monitoring data from {csv_file}")

        # Read CSV file
        df = pd.read_csv(csv_file)

        # Convert timestamp column
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], format='%m/%d/%Y %H:%M')

        async with get_db() as session:
            for _, row in df.iterrows():
                try:
                    # Extract user ID from Device-ID/User-ID column
                    user_id = self._extract_user_id(row['Device-ID/User-ID'])

                    # Check if user exists, create if not
                    await self._ensure_user_exists(user_id, session)

                    # Prepare safety record data
                    record_data = {
                        "user_id": user_id,
                        "timestamp": row['Timestamp'].to_pydatetime(),
                        "movement_activity": self._parse_movement_activity(row['Movement Activity']),
                        "fall_detected": row['Fall Detected (Yes/No)'] == 'Yes',
                        "impact_force": row['Impact Force Level'] if pd.notna(row['Impact Force Level']) else None,
                        "post_fall_inactivity_duration": row['Post-Fall Inactivity Duration (Seconds)'] if pd.notna(row['Post-Fall Inactivity Duration (Seconds)']) else 0,
                        "location_room": row['Location'] if pd.notna(row['Location']) else None,
                        "device_type": "safety_monitor",
                        "safety_alert": row['Alert Triggered (Yes/No)'] == 'Yes',
                        "caregiver_notified": row['Caregiver Notified (Yes/No)'] == 'Yes'
                    }

                    # Create safety record
                    await create_safety_record(record_data, session)

                except Exception as e:
                    logger.error(f"Error processing safety record: {e}")
                    continue

        logger.info(f"Ingested {len(df)} safety monitoring records")

    async def ingest_reminder_data(self):
        """Ingest reminder data from CSV"""
        csv_file = self.data_directory / "daily_reminder.csv"

        if not csv_file.exists():
            logger.warning(f"Reminder CSV file not found: {csv_file}")
            return

        logger.info(f"Reading reminder data from {csv_file}")

        # Read CSV file
        df = pd.read_csv(csv_file)

        # Convert timestamp column
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], format='%m/%d/%Y %H:%M')

        async with get_db() as session:
            for _, row in df.iterrows():
                try:
                    # Extract user ID from Device-ID/User-ID column
                    user_id = self._extract_user_id(row['Device-ID/User-ID'])

                    # Check if user exists, create if not
                    await self._ensure_user_exists(user_id, session)

                    # Parse reminder type
                    reminder_type = self._parse_reminder_type(row['Reminder Type'])

                    # Create reminder
                    reminder = Reminder(
                        user_id=user_id,
                        reminder_type=reminder_type,
                        title=row['Reminder Type'],
                        description=f"{row['Reminder Type']} reminder",
                        scheduled_time=row['Timestamp'].to_pydatetime(),
                        is_sent=row['Reminder Sent (Yes/No)'] == 'Yes',
                        is_acknowledged=row['Acknowledged (Yes/No)'] == 'Yes'
                    )

                    session.add(reminder)
                    await session.commit()

                except Exception as e:
                    logger.error(f"Error processing reminder record: {e}")
                    continue

        logger.info(f"Ingested {len(df)} reminder records")

    async def create_sample_users(self):
        """Create sample users for demonstration"""
        sample_users = [
            {
                "device_id": "D1000",
                "full_name": "John Smith",
                "role": "elderly",
                "email": "john.smith@email.com",
                "phone": "+1234567890",
                "date_of_birth": datetime(1955, 3, 15),
                "medical_conditions": ["Hypertension", "Diabetes"],
                "medications": ["Lisinopril", "Metformin"],
                "allergies": ["Penicillin"],
                "emergency_contacts": ["+1987654321"]
            },
            {
                "device_id": "D1001",
                "full_name": "Mary Johnson",
                "role": "elderly",
                "email": "mary.johnson@email.com",
                "phone": "+1234567891",
                "date_of_birth": datetime(1960, 7, 22),
                "medical_conditions": ["Arthritis"],
                "medications": ["Ibuprofen"],
                "allergies": [],
                "emergency_contacts": ["+1987654322"]
            },
            {
                "device_id": "D1002",
                "full_name": "Robert Davis",
                "role": "caregiver",
                "email": "robert.davis@email.com",
                "phone": "+1234567892",
                "date_of_birth": datetime(1980, 11, 8),
                "medical_conditions": [],
                "medications": [],
                "allergies": [],
                "emergency_contacts": []
            },
            {
                "device_id": "D1003",
                "full_name": "Dr. Sarah Wilson",
                "role": "healthcare_provider",
                "email": "sarah.wilson@email.com",
                "phone": "+1234567893",
                "date_of_birth": datetime(1975, 1, 20),
                "medical_conditions": [],
                "medications": [],
                "allergies": [],
                "emergency_contacts": []
            }
        ]

        async with get_db() as session:
            for user_data in sample_users:
                try:
                    # Check if user already exists
                    from sqlalchemy import select
                    result = await session.execute(
                        select(User).where(User.device_id == user_data["device_id"])
                    )
                    existing_user = result.scalar_one_or_none()

                    if not existing_user:
                        user = User(**user_data)
                        session.add(user)
                        logger.info(f"Created sample user: {user_data['full_name']}")
                    else:
                        logger.info(f"User already exists: {user_data['full_name']}")

                except Exception as e:
                    logger.error(f"Error creating sample user {user_data['full_name']}: {e}")
                    continue

            await session.commit()

        logger.info("Sample users creation completed")

    def _extract_user_id(self, device_user_id: str) -> int:
        """Extract numeric user ID from device-user ID string"""
        # For demo purposes, map device IDs to numeric IDs
        device_mapping = {
            "D1000": 1,
            "D1001": 2,
            "D1002": 3,
            "D1003": 4
        }

        # Extract device ID part
        device_id = device_user_id.split('/')[0] if '/' in device_user_id else device_user_id

        return device_mapping.get(device_id, hash(device_id) % 1000 + 100)

    async def _ensure_user_exists(self, user_id: int, session):
        """Ensure user exists in database"""
        from sqlalchemy import select
        from backend.models import User

        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            # Create a basic user record
            user = User(
                id=user_id,
                device_id=f"D{user_id:04d}",
                full_name=f"User {user_id}",
                role="elderly",
                is_active=True
            )
            session.add(user)
            await session.flush()

    def _parse_blood_pressure(self, bp_string: str, component: str) -> int:
        """Parse blood pressure string (e.g., '120/80 mmHg')"""
        if pd.isna(bp_string) or not isinstance(bp_string, str):
            return None

        try:
            parts = bp_string.replace('mmHg', '').strip().split('/')
            if len(parts) == 2:
                systolic = int(parts[0].strip())
                diastolic = int(parts[1].strip())

                if component == 'systolic':
                    return systolic
                elif component == 'diastolic':
                    return diastolic
        except (ValueError, IndexError):
            pass

        return None

    def _parse_movement_activity(self, activity_string: str):
        """Parse movement activity string"""
        if pd.isna(activity_string) or not isinstance(activity_string, str):
            return None

        # Map CSV values to enum values
        activity_mapping = {
            "Walking": "walking",
            "Running": "running",
            "Lying": "lying",
            "Sitting": "sitting",
            "Standing": "standing",
            "No Movement": "no_movement"
        }

        return activity_mapping.get(activity_string, activity_string.lower().replace(' ', '_'))

    def _parse_reminder_type(self, reminder_string: str) -> ReminderType:
        """Parse reminder type string"""
        if pd.isna(reminder_string) or not isinstance(reminder_string, str):
            return ReminderType.OTHER

        # Map CSV values to enum values
        type_mapping = {
            "Exercise": ReminderType.EXERCISE,
            "Hydration": ReminderType.HYDRATION,
            "Appointment": ReminderType.APPOINTMENT,
            "Medication": ReminderType.MEDICATION,
            "Meal": ReminderType.MEAL
        }

        return type_mapping.get(reminder_string, ReminderType.OTHER)

async def main():
    """Main function to run data ingestion"""
    # Create data directory if it doesn't exist
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    # Copy CSV files to data directory
    import shutil
    csv_files = [
        "daily_reminder.csv",
        "health_monitoring.csv",
        "safety_monitoring.csv"
    ]

    for csv_file in csv_files:
        source = Path(csv_file)
        if source.exists():
            shutil.copy(source, data_dir / csv_file)
            logger.info(f"Copied {csv_file} to data directory")
        else:
            logger.warning(f"Source CSV file not found: {csv_file}")

    # Initialize data ingestion service
    ingestion_service = DataIngestionService()

    # Run data ingestion
    await ingestion_service.ingest_all_data()

    logger.info("Data ingestion process completed")

if __name__ == "__main__":
    asyncio.run(main())
