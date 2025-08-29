# FastAPI Backend for Elderly Care AI System

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from contextlib import asynccontextmanager
import asyncio
from datetime import datetime
import logging

# Import routers and services
from .routers import (
    health_monitoring,
    safety_monitoring,
    reminders,
    alerts,
    users,
    dashboard
)
from .database import init_db, get_db
from .agents import agent_coordinator
from .config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Lifespan context manager for startup/shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Elderly Care AI System...")

    # Initialize database
    await init_db()

    # Start agent coordinator
    await agent_coordinator.start_agents()

    logger.info("System started successfully")

    yield

    # Shutdown
    logger.info("Shutting down Elderly Care AI System...")

    # Stop agents
    await agent_coordinator.stop_agents()

    logger.info("System shutdown complete")

# Create FastAPI app
app = FastAPI(
    title="Elderly Care AI System",
    description="Multi-agent AI system for elderly care and support",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer()

# Include routers
app.include_router(
    health_monitoring.router,
    prefix="/api/v1/health",
    tags=["Health Monitoring"]
)

app.include_router(
    safety_monitoring.router,
    prefix="/api/v1/safety",
    tags=["Safety Monitoring"]
)

app.include_router(
    reminders.router,
    prefix="/api/v1/reminders",
    tags=["Reminders"]
)

app.include_router(
    alerts.router,
    prefix="/api/v1/alerts",
    tags=["Alerts"]
)

app.include_router(
    users.router,
    prefix="/api/v1/users",
    tags=["Users"]
)

app.include_router(
    dashboard.router,
    prefix="/api/v1/dashboard",
    tags=["Dashboard"]
)

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Elderly Care AI System API",
        "version": "1.0.0",
        "status": "running",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "database": "connected",
            "agents": "running",
            "cache": "connected"
        }
    }

@app.get("/api/v1/system/status")
async def system_status():
    """Get comprehensive system status"""
    return {
        "system": {
            "name": "Elderly Care AI System",
            "version": "1.0.0",
            "status": "operational"
        },
        "agents": await agent_coordinator.get_agent_status(),
        "database": await get_db().health_check(),
        "timestamp": datetime.utcnow().isoformat()
    }

# WebSocket endpoint for real-time updates
from fastapi import WebSocket, WebSocketDisconnect
from .websocket_manager import websocket_manager

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """WebSocket endpoint for real-time communication"""
    await websocket_manager.connect(websocket, client_id)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle incoming messages
            await websocket_manager.handle_message(client_id, data)
    except WebSocketDisconnect:
        websocket_manager.disconnect(client_id)
        logger.info(f"Client {client_id} disconnected")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
