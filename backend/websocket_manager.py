# WebSocket Manager for Real-time Communication

import asyncio
import json
import logging
from typing import Dict, Set, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class WebSocketManager:
    """Manages WebSocket connections for real-time communication"""

    def __init__(self):
        self.active_connections: Dict[str, Set] = {}  # client_id -> set of connections
        self.user_connections: Dict[int, Set] = {}   # user_id -> set of client_ids

    async def connect(self, websocket, client_id: str):
        """Connect a new WebSocket client"""
        if client_id not in self.active_connections:
            self.active_connections[client_id] = set()

        self.active_connections[client_id].add(websocket)

        logger.info(f"WebSocket client {client_id} connected")

        # Send welcome message
        try:
            await websocket.send_json({
                "type": "connection_established",
                "client_id": client_id,
                "timestamp": datetime.utcnow().isoformat(),
                "message": "Connected to Elderly Care AI System"
            })
        except Exception as e:
            logger.error(f"Failed to send welcome message to {client_id}: {e}")

    def disconnect(self, client_id: str):
        """Disconnect a WebSocket client"""
        if client_id in self.active_connections:
            self.active_connections[client_id].clear()
            del self.active_connections[client_id]

            logger.info(f"WebSocket client {client_id} disconnected")

    async def broadcast_to_user(self, user_id: int, message: Dict):
        """Broadcast message to all clients connected for a specific user"""
        # Find client_ids for this user
        client_ids = []
        for client_id, connections in self.active_connections.items():
            if connections:  # Only if there are active connections
                client_ids.append(client_id)

        # For now, broadcast to all connected clients
        # In a real implementation, you'd map user_id to client_ids
        sent_count = 0
        for client_id in client_ids:
            if await self._send_to_client(client_id, message):
                sent_count += 1

        if sent_count > 0:
            logger.debug(f"Broadcasted message to {sent_count} clients for user {user_id}")

    async def send_to_client(self, client_id: str, message: Dict):
        """Send message to a specific client"""
        success = await self._send_to_client(client_id, message)
        if success:
            logger.debug(f"Sent message to client {client_id}")
        else:
            logger.warning(f"Failed to send message to client {client_id}")

    async def _send_to_client(self, client_id: str, message: Dict) -> bool:
        """Send message to a client (internal method)"""
        if client_id not in self.active_connections:
            return False

        success = False
        failed_connections = []

        for websocket in self.active_connections[client_id]:
            try:
                await websocket.send_json(message)
                success = True
            except Exception as e:
                logger.error(f"Failed to send message to websocket for {client_id}: {e}")
                failed_connections.append(websocket)

        # Remove failed connections
        for websocket in failed_connections:
            self.active_connections[client_id].discard(websocket)

        # Clean up empty client sets
        if not self.active_connections[client_id]:
            del self.active_connections[client_id]

        return success

    async def broadcast_to_all(self, message: Dict):
        """Broadcast message to all connected clients"""
        sent_count = 0
        for client_id in list(self.active_connections.keys()):
            if await self._send_to_client(client_id, message):
                sent_count += 1

        logger.debug(f"Broadcasted message to {sent_count} clients")

    async def handle_message(self, client_id: str, message: str):
        """Handle incoming message from client"""
        try:
            data = json.loads(message)

            # Handle different message types
            message_type = data.get("type")

            if message_type == "ping":
                await self._send_to_client(client_id, {
                    "type": "pong",
                    "timestamp": datetime.utcnow().isoformat()
                })

            elif message_type == "acknowledge_reminder":
                await self._handle_reminder_acknowledgment(client_id, data)

            elif message_type == "request_status":
                await self._handle_status_request(client_id, data)

            else:
                logger.warning(f"Unknown message type from {client_id}: {message_type}")

        except json.JSONDecodeError:
            logger.error(f"Invalid JSON message from {client_id}: {message}")
        except Exception as e:
            logger.error(f"Error handling message from {client_id}: {e}")

    async def _handle_reminder_acknowledgment(self, client_id: str, data: Dict):
        """Handle reminder acknowledgment from client"""
        try:
            reminder_id = data.get("reminder_id")
            user_id = data.get("user_id")

            if reminder_id and user_id:
                # Import here to avoid circular imports
                from .agents.coordinator import agent_coordinator

                success = await agent_coordinator.reminder_agent.acknowledge_reminder(reminder_id, user_id)

                await self._send_to_client(client_id, {
                    "type": "reminder_acknowledged",
                    "reminder_id": reminder_id,
                    "success": success,
                    "timestamp": datetime.utcnow().isoformat()
                })

        except Exception as e:
            logger.error(f"Error handling reminder acknowledgment: {e}")

    async def _handle_status_request(self, client_id: str, data: Dict):
        """Handle status request from client"""
        try:
            user_id = data.get("user_id")
            request_type = data.get("request_type", "general")

            status_data = {
                "type": "status_response",
                "request_type": request_type,
                "timestamp": datetime.utcnow().isoformat()
            }

            if request_type == "health":
                # Get health status
                from .agents.coordinator import agent_coordinator
                status_data["health_status"] = await agent_coordinator.agents["health"].get_status()

            elif request_type == "safety":
                # Get safety status
                from .agents.coordinator import agent_coordinator
                status_data["safety_status"] = await agent_coordinator.agents["safety"].get_status()

            elif request_type == "reminders":
                # Get reminder status
                from .agents.coordinator import agent_coordinator
                status_data["reminder_status"] = await agent_coordinator.agents["reminder"].get_status()

            elif request_type == "system":
                # Get overall system status
                from .agents.coordinator import agent_coordinator
                status_data["system_status"] = await agent_coordinator.get_agent_status()

            await self._send_to_client(client_id, status_data)

        except Exception as e:
            logger.error(f"Error handling status request: {e}")

    def get_connection_count(self) -> int:
        """Get total number of active connections"""
        return sum(len(connections) for connections in self.active_connections.values())

    def get_client_count(self) -> int:
        """Get number of unique clients connected"""
        return len(self.active_connections)

    def get_stats(self) -> Dict:
        """Get WebSocket connection statistics"""
        return {
            "total_connections": self.get_connection_count(),
            "unique_clients": self.get_client_count(),
            "clients": list(self.active_connections.keys()),
            "timestamp": datetime.utcnow().isoformat()
        }

# Global WebSocket manager instance
websocket_manager = WebSocketManager()
