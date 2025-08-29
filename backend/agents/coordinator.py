# Agent Coordinator for Elderly Care AI System

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import json

from .config import settings
from .database import get_db, get_pending_reminders, get_recent_health_records, get_recent_safety_records
from .models import Alert, AlertPriority, AlertType, User
from .websocket_manager import websocket_manager

logger = logging.getLogger(__name__)

class AgentCoordinator:
    """Coordinates multiple AI agents for elderly care system"""

    def __init__(self):
        self.agents = {}
        self.is_running = False
        self.tasks = []

    async def start_agents(self):
        """Start all configured agents"""
        logger.info("Starting AI agents...")

        if settings.health_agent_enabled:
            from .agents.health_agent import HealthMonitoringAgent
            self.agents["health"] = HealthMonitoringAgent()
            await self.agents["health"].start()
            logger.info("Health Monitoring Agent started")

        if settings.safety_agent_enabled:
            from .agents.safety_agent import SafetyMonitoringAgent
            self.agents["safety"] = SafetyMonitoringAgent()
            await self.agents["safety"].start()
            logger.info("Safety Monitoring Agent started")

        if settings.reminder_agent_enabled:
            from .agents.reminder_agent import ReminderAgent
            self.agents["reminder"] = ReminderAgent()
            await self.agents["reminder"].start()
            logger.info("Reminder Agent started")

        self.is_running = True

        # Start background tasks
        self.tasks = [
            asyncio.create_task(self._health_check_loop()),
            asyncio.create_task(self._process_pending_reminders()),
            asyncio.create_task(self._analyze_health_trends()),
            asyncio.create_task(self._monitor_system_alerts()),
        ]

        logger.info(f"All agents started successfully. Running agents: {list(self.agents.keys())}")

    async def stop_agents(self):
        """Stop all running agents"""
        logger.info("Stopping AI agents...")

        # Cancel background tasks
        for task in self.tasks:
            task.cancel()

        # Stop individual agents
        for agent_name, agent in self.agents.items():
            try:
                await agent.stop()
                logger.info(f"{agent_name} agent stopped")
            except Exception as e:
                logger.error(f"Error stopping {agent_name} agent: {e}")

        self.agents.clear()
        self.is_running = False
        logger.info("All agents stopped")

    async def get_agent_status(self) -> Dict[str, Any]:
        """Get status of all agents"""
        status = {
            "total_agents": len(self.agents),
            "running_agents": [name for name in self.agents.keys()],
            "agent_details": {}
        }

        for agent_name, agent in self.agents.items():
            try:
                agent_status = await agent.get_status()
                status["agent_details"][agent_name] = agent_status
            except Exception as e:
                status["agent_details"][agent_name] = {
                    "status": "error",
                    "error": str(e)
                }

        return status

    async def process_health_data(self, user_id: int, data: Dict[str, Any]):
        """Process incoming health data"""
        if "health" in self.agents:
            await self.agents["health"].process_data(user_id, data)

    async def process_safety_data(self, user_id: int, data: Dict[str, Any]):
        """Process incoming safety data"""
        if "safety" in self.agents:
            await self.agents["safety"].process_data(user_id, data)

    async def create_reminder(self, user_id: int, reminder_data: Dict[str, Any]):
        """Create a new reminder"""
        if "reminder" in self.agents:
            return await self.agents["reminder"].create_reminder(user_id, reminder_data)
        return None

    async def _health_check_loop(self):
        """Periodic health check for all agents"""
        while self.is_running:
            try:
                for agent_name, agent in self.agents.items():
                    health_status = await agent.health_check()
                    if not health_status["healthy"]:
                        logger.warning(f"Agent {agent_name} health check failed: {health_status}")

                        # Create system alert
                        await self._create_system_alert(
                            f"Agent {agent_name} health check failed",
                            f"Agent {agent_name} is not responding properly: {health_status}",
                            AlertPriority.HIGH
                        )

                await asyncio.sleep(300)  # Check every 5 minutes
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check loop error: {e}")
                await asyncio.sleep(60)  # Wait before retry

    async def _process_pending_reminders(self):
        """Process pending reminders"""
        while self.is_running:
            try:
                async with get_db() as session:
                    pending_reminders = await get_pending_reminders(session)

                    for reminder in pending_reminders:
                        if "reminder" in self.agents:
                            await self.agents["reminder"].send_reminder(reminder)

                await asyncio.sleep(60)  # Check every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Pending reminders processing error: {e}")
                await asyncio.sleep(60)

    async def _analyze_health_trends(self):
        """Analyze health trends and create predictive alerts"""
        while self.is_running:
            try:
                async with get_db() as session:
                    # Get all active users
                    from sqlalchemy import select
                    result = await session.execute(
                        select(User).where(User.is_active == True)
                    )
                    users = result.scalars().all()

                    for user in users:
                        # Get recent health records
                        health_records = await get_recent_health_records(user.id, limit=50, session=session)

                        if len(health_records) >= 10:  # Need minimum data for analysis
                            # Analyze trends
                            trends = await self._analyze_user_health_trends(user.id, health_records)

                            # Create alerts for concerning trends
                            if trends["needs_attention"]:
                                await self._create_health_alert(
                                    user.id,
                                    "Health Trend Alert",
                                    f"Concerning health trends detected: {trends['summary']}",
                                    AlertPriority.MEDIUM
                                )

                await asyncio.sleep(3600)  # Analyze every hour
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health trend analysis error: {e}")
                await asyncio.sleep(300)

    async def _analyze_user_health_trends(self, user_id: int, health_records: List) -> Dict[str, Any]:
        """Analyze health trends for a specific user"""
        # This would use ML models for predictive analysis
        # For now, implement basic trend analysis

        trends = {
            "needs_attention": False,
            "summary": "",
            "metrics": {}
        }

        if not health_records:
            return trends

        # Analyze heart rate trends
        heart_rates = [r.heart_rate for r in health_records if r.heart_rate]
        if heart_rates:
            avg_hr = sum(heart_rates) / len(heart_rates)
            if avg_hr > settings.heart_rate_max or avg_hr < settings.heart_rate_min:
                trends["needs_attention"] = True
                trends["summary"] += f"Average heart rate ({avg_hr:.1f}) outside normal range. "

        # Analyze blood pressure trends
        systolic_values = [r.blood_pressure_systolic for r in health_records if r.blood_pressure_systolic]
        if systolic_values:
            avg_systolic = sum(systolic_values) / len(systolic_values)
            if avg_systolic > settings.blood_pressure_systolic_max:
                trends["needs_attention"] = True
                trends["summary"] += f"Elevated blood pressure average ({avg_systolic:.1f}). "

        return trends

    async def _monitor_system_alerts(self):
        """Monitor and escalate system alerts"""
        while self.is_running:
            try:
                async with get_db() as session:
                    from .database import get_active_alerts
                    active_alerts = await get_active_alerts(session)

                    for alert in active_alerts:
                        # Check if alert needs escalation
                        age_hours = (datetime.utcnow() - alert.created_at).total_seconds() / 3600

                        if age_hours > 1 and not alert.is_resolved:
                            # Escalate alert
                            await self._escalate_alert(alert)

                await asyncio.sleep(600)  # Check every 10 minutes
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"System alert monitoring error: {e}")
                await asyncio.sleep(300)

    async def _create_health_alert(self, user_id: int, title: str, message: str, priority: AlertPriority):
        """Create a health alert"""
        async with get_db() as session:
            alert = Alert(
                user_id=user_id,
                alert_type=AlertType.HEALTH,
                priority=priority,
                title=title,
                message=message
            )
            session.add(alert)
            await session.commit()

            # Notify via WebSocket
            await websocket_manager.broadcast_to_user(user_id, {
                "type": "alert",
                "alert_type": "health",
                "title": title,
                "message": message,
                "priority": priority.value
            })

    async def _create_system_alert(self, title: str, message: str, priority: AlertPriority):
        """Create a system alert"""
        async with get_db() as session:
            alert = Alert(
                user_id=1,  # System user
                alert_type=AlertType.SYSTEM,
                priority=priority,
                title=title,
                message=message
            )
            session.add(alert)
            await session.commit()

    async def _escalate_alert(self, alert: Alert):
        """Escalate an unresolved alert"""
        async with get_db() as session:
            alert.escalation_level += 1

            if alert.escalation_level >= alert.max_escalation_level:
                alert.priority = AlertPriority.CRITICAL

            await session.commit()

# Global agent coordinator instance
agent_coordinator = AgentCoordinator()
