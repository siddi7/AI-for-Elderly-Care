# Reminder Agent for Elderly Care AI System

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import json

from ..config import settings
from ..database import get_db, get_user_by_id
from ..models import Alert, AlertPriority, AlertType, Reminder, ReminderType
from ..websocket_manager import websocket_manager

logger = logging.getLogger(__name__)

class ReminderAgent:
    """AI agent for managing medication and activity reminders"""

    def __init__(self):
        self.is_running = False
        self.voice_synthesis_enabled = False
        self.notification_providers = {}

    async def start(self):
        """Start the reminder agent"""
        logger.info("Starting Reminder Agent...")
        self.is_running = True

        # Initialize notification providers
        await self._initialize_notification_providers()

        logger.info("Reminder Agent started successfully")

    async def stop(self):
        """Stop the reminder agent"""
        logger.info("Stopping Reminder Agent...")
        self.is_running = False
        logger.info("Reminder Agent stopped")

    async def health_check(self) -> Dict[str, Any]:
        """Health check for the agent"""
        return {
            "healthy": self.is_running,
            "voice_enabled": self.voice_synthesis_enabled,
            "notification_providers": list(self.notification_providers.keys())
        }

    async def get_status(self) -> Dict[str, Any]:
        """Get agent status"""
        return {
            "name": "Reminder Agent",
            "status": "running" if self.is_running else "stopped",
            "voice_synthesis": self.voice_synthesis_enabled,
            "active_reminders": await self._count_active_reminders()
        }

    async def create_reminder(self, user_id: int, reminder_data: Dict[str, Any]) -> Optional[Reminder]:
        """Create a new reminder"""
        try:
            async with get_db() as session:
                # Validate user
                user = await get_user_by_id(user_id, session)
                if not user:
                    logger.warning(f"User {user_id} not found")
                    return None

                # Validate reminder data
                validated_data = self._validate_reminder_data(reminder_data)

                # Create reminder
                reminder = Reminder(
                    user_id=user_id,
                    **validated_data
                )

                session.add(reminder)
                await session.commit()
                await session.refresh(reminder)

                logger.info(f"Created reminder {reminder.id} for user {user_id}")

                # Schedule the reminder
                await self._schedule_reminder(reminder)

                return reminder

        except Exception as e:
            logger.error(f"Failed to create reminder for user {user_id}: {e}")
            return None

    async def send_reminder(self, reminder: Reminder):
        """Send a reminder notification"""
        try:
            async with get_db() as session:
                # Check if reminder is still active
                if reminder.is_acknowledged or reminder.escalation_attempts >= reminder.max_escalation_attempts:
                    logger.info(f"Reminder {reminder.id} is no longer active")
                    return

                # Prepare reminder message
                message_data = await self._prepare_reminder_message(reminder, session)

                # Send notifications
                success = await self._send_notifications(reminder.user_id, message_data)

                if success:
                    reminder.is_sent = True
                    reminder.escalation_attempts += 1
                    await session.commit()

                    # Send real-time update
                    await self._send_realtime_update(reminder.user_id, reminder, "sent")

                    logger.info(f"Sent reminder {reminder.id} to user {reminder.user_id}")
                else:
                    logger.error(f"Failed to send reminder {reminder.id}")

        except Exception as e:
            logger.error(f"Error sending reminder {reminder.id}: {e}")

    async def acknowledge_reminder(self, reminder_id: int, user_id: int) -> bool:
        """Acknowledge a reminder"""
        try:
            async with get_db() as session:
                from sqlalchemy import select

                result = await session.execute(
                    select(Reminder).where(
                        Reminder.id == reminder_id,
                        Reminder.user_id == user_id
                    )
                )
                reminder = result.scalar_one_or_none()

                if not reminder:
                    return False

                reminder.is_acknowledged = True
                reminder.acknowledged_at = datetime.utcnow()
                await session.commit()

                # Send real-time update
                await self._send_realtime_update(user_id, reminder, "acknowledged")

                logger.info(f"Reminder {reminder_id} acknowledged by user {user_id}")
                return True

        except Exception as e:
            logger.error(f"Failed to acknowledge reminder {reminder_id}: {e}")
            return False

    def _validate_reminder_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate reminder data"""
        validated = {}

        # Required fields
        if "reminder_type" in data:
            reminder_type = data["reminder_type"]
            if isinstance(reminder_type, str):
                validated["reminder_type"] = ReminderType(reminder_type)
            elif isinstance(reminder_type, ReminderType):
                validated["reminder_type"] = reminder_type

        if "title" in data:
            validated["title"] = str(data["title"])[:255]

        if "scheduled_time" in data:
            scheduled_time = data["scheduled_time"]
            if isinstance(scheduled_time, str):
                validated["scheduled_time"] = datetime.fromisoformat(scheduled_time.replace('Z', '+00:00'))
            elif isinstance(scheduled_time, datetime):
                validated["scheduled_time"] = scheduled_time

        # Optional fields
        if "description" in data:
            validated["description"] = str(data["description"])[:1000]

        if "is_recurring" in data:
            validated["is_recurring"] = bool(data["is_recurring"])

        if "recurrence_pattern" in data:
            validated["recurrence_pattern"] = json.dumps(data["recurrence_pattern"])

        if "voice_enabled" in data:
            validated["voice_enabled"] = bool(data["voice_enabled"])
        else:
            validated["voice_enabled"] = settings.voice_reminder_enabled

        return validated

    async def _prepare_reminder_message(self, reminder: Reminder, session) -> Dict[str, Any]:
        """Prepare reminder message for sending"""
        message_data = {
            "reminder_id": reminder.id,
            "type": reminder.reminder_type.value,
            "title": reminder.title,
            "description": reminder.description,
            "scheduled_time": reminder.scheduled_time.isoformat(),
            "voice_enabled": reminder.voice_enabled,
            "escalation_attempt": reminder.escalation_attempts + 1
        }

        # Add type-specific information
        if reminder.reminder_type == ReminderType.MEDICATION:
            message_data["message"] = f"It's time to take your medication: {reminder.title}"
            message_data["voice_message"] = f"Hello, it's time to take your {reminder.title} medication."

        elif reminder.reminder_type == ReminderType.APPOINTMENT:
            message_data["message"] = f"You have an appointment: {reminder.title}"
            message_data["voice_message"] = f"Hello, you have an appointment for {reminder.title}."

        elif reminder.reminder_type == ReminderType.EXERCISE:
            message_data["message"] = f"Time for exercise: {reminder.title}"
            message_data["voice_message"] = f"Hello, it's time for your exercise: {reminder.title}."

        elif reminder.reminder_type == ReminderType.HYDRATION:
            message_data["message"] = f"Time to drink water: {reminder.title}"
            message_data["voice_message"] = f"Hello, it's time to drink water. {reminder.title}"

        elif reminder.reminder_type == ReminderType.MEAL:
            message_data["message"] = f"Time for meal: {reminder.title}"
            message_data["voice_message"] = f"Hello, it's time for your meal: {reminder.title}."

        else:
            message_data["message"] = reminder.title
            message_data["voice_message"] = f"Hello, {reminder.title}"

        # Add escalation message if this is a retry
        if reminder.escalation_attempts > 0:
            escalation_msg = f" (Attempt {reminder.escalation_attempts + 1})"
            message_data["message"] += escalation_msg
            message_data["voice_message"] += escalation_msg

        return message_data

    async def _send_notifications(self, user_id: int, message_data: Dict[str, Any]) -> bool:
        """Send reminder notifications through various channels"""
        success = False

        try:
            # Send via WebSocket (real-time)
            websocket_success = await self._send_websocket_notification(user_id, message_data)
            if websocket_success:
                success = True

            # Send SMS if configured
            if settings.twilio_phone_number and user_id in self.notification_providers.get("sms", []):
                sms_success = await self._send_sms_notification(user_id, message_data)
                if sms_success:
                    success = True

            # Send email if configured
            if settings.sendgrid_api_key:
                email_success = await self._send_email_notification(user_id, message_data)
                if email_success:
                    success = True

            # Send voice call if enabled and configured
            if (message_data.get("voice_enabled") and
                settings.twilio_phone_number and
                reminder.escalation_attempts >= 1):  # Only for escalations
                voice_success = await self._send_voice_notification(user_id, message_data)
                if voice_success:
                    success = True

        except Exception as e:
            logger.error(f"Error sending notifications for user {user_id}: {e}")

        return success

    async def _send_websocket_notification(self, user_id: int, message_data: Dict[str, Any]) -> bool:
        """Send reminder via WebSocket"""
        try:
            notification = {
                "type": "reminder",
                "reminder_id": message_data["reminder_id"],
                "message": message_data["message"],
                "voice_message": message_data.get("voice_message"),
                "timestamp": datetime.utcnow().isoformat()
            }

            await websocket_manager.broadcast_to_user(user_id, notification)
            return True

        except Exception as e:
            logger.error(f"WebSocket notification failed for user {user_id}: {e}")
            return False

    async def _send_sms_notification(self, user_id: int, message_data: Dict[str, Any]) -> bool:
        """Send reminder via SMS"""
        try:
            # This would integrate with Twilio
            logger.info(f"SMS notification for user {user_id}: {message_data['message']}")

            # TODO: Implement actual SMS sending
            # from twilio.rest import Client
            # client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
            # message = client.messages.create(
            #     body=message_data["message"],
            #     from_=settings.twilio_phone_number,
            #     to=user_phone_number
            # )

            return True

        except Exception as e:
            logger.error(f"SMS notification failed for user {user_id}: {e}")
            return False

    async def _send_email_notification(self, user_id: int, message_data: Dict[str, Any]) -> bool:
        """Send reminder via email"""
        try:
            # This would integrate with SendGrid
            logger.info(f"Email notification for user {user_id}: {message_data['message']}")

            # TODO: Implement actual email sending
            # from sendgrid import SendGridAPIClient
            # from sendgrid.helpers.mail import Mail

            return True

        except Exception as e:
            logger.error(f"Email notification failed for user {user_id}: {e}")
            return False

    async def _send_voice_notification(self, user_id: int, message_data: Dict[str, Any]) -> bool:
        """Send reminder via voice call"""
        try:
            # This would integrate with Twilio for voice calls
            logger.info(f"Voice notification for user {user_id}: {message_data['voice_message']}")

            # TODO: Implement actual voice calling
            # from twilio.twiml.voice_response import VoiceResponse
            # response = VoiceResponse()
            # response.say(message_data["voice_message"])

            return True

        except Exception as e:
            logger.error(f"Voice notification failed for user {user_id}: {e}")
            return False

    async def _initialize_notification_providers(self):
        """Initialize notification providers"""
        try:
            # Check available providers
            if settings.twilio_account_sid and settings.twilio_auth_token:
                self.notification_providers["sms"] = []
                self.notification_providers["voice"] = []
                logger.info("Twilio SMS and voice services initialized")

            if settings.sendgrid_api_key:
                self.notification_providers["email"] = []
                logger.info("SendGrid email service initialized")

            if settings.telegram_bot_token:
                self.notification_providers["telegram"] = []
                logger.info("Telegram bot service initialized")

        except Exception as e:
            logger.error(f"Failed to initialize notification providers: {e}")

    async def _schedule_reminder(self, reminder: Reminder):
        """Schedule a reminder for processing"""
        # This would integrate with a task scheduler like Celery
        # For now, reminders are processed by the coordinator's loop
        logger.info(f"Scheduled reminder {reminder.id} for {reminder.scheduled_time}")

    async def _count_active_reminders(self) -> int:
        """Count active reminders"""
        try:
            async with get_db() as session:
                from sqlalchemy import select, func

                result = await session.execute(
                    select(func.count(Reminder.id)).where(
                        Reminder.is_acknowledged == False,
                        Reminder.scheduled_time <= datetime.utcnow()
                    )
                )

                return result.scalar() or 0

        except Exception as e:
            logger.error(f"Failed to count active reminders: {e}")
            return 0

    async def _send_realtime_update(self, user_id: int, reminder: Reminder, action: str):
        """Send real-time reminder updates via WebSocket"""
        try:
            update_data = {
                "type": "reminder_update",
                "reminder_id": reminder.id,
                "action": action,
                "reminder_type": reminder.reminder_type.value,
                "title": reminder.title,
                "timestamp": datetime.utcnow().isoformat()
            }

            await websocket_manager.broadcast_to_user(user_id, update_data)

        except Exception as e:
            logger.error(f"Failed to send reminder update: {e}")

    async def get_user_reminders(self, user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Get reminders for a user"""
        try:
            async with get_db() as session:
                from sqlalchemy import select

                result = await session.execute(
                    select(Reminder).where(Reminder.user_id == user_id)
                    .order_by(Reminder.scheduled_time.desc())
                    .limit(limit)
                )

                reminders = result.scalars().all()

                return [{
                    "id": r.id,
                    "type": r.reminder_type.value,
                    "title": r.title,
                    "description": r.description,
                    "scheduled_time": r.scheduled_time.isoformat(),
                    "is_sent": r.is_sent,
                    "is_acknowledged": r.is_acknowledged,
                    "acknowledged_at": r.acknowledged_at.isoformat() if r.acknowledged_at else None,
                    "escalation_attempts": r.escalation_attempts
                } for r in reminders]

        except Exception as e:
            logger.error(f"Failed to get reminders for user {user_id}: {e}")
            return []
