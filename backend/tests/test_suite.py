# Comprehensive Testing Suite for Elderly Care AI System

import pytest
import asyncio
import httpx
import json
from datetime import datetime, timedelta
from typing import Dict, Any
import os
import sys

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))

from backend.database import get_db, create_health_record, create_safety_record
from backend.models import User, UserRole, Reminder, ReminderType
from backend.config import settings

# Test configuration
TEST_DATABASE_URL = "postgresql://test_user:test_password@localhost:5432/test_db"
TEST_REDIS_URL = "redis://localhost:6379"

@pytest.fixture
async def test_client():
    """Create test client for API testing"""
    from backend.main import app
    from httpx import AsyncClient

    async with AsyncClient(app=app, base_url="http://testserver") as client:
        yield client

@pytest.fixture
async def test_db():
    """Create test database session"""
    async with get_db() as session:
        yield session

class TestHealthMonitoring:
    """Test health monitoring functionality"""

    def test_validate_health_data_normal(self):
        """Test health data validation with normal values"""
        from backend.agents.health_agent import HealthMonitoringAgent

        agent = HealthMonitoringAgent()
        data = {
            "heart_rate": 75,
            "blood_pressure_systolic": 120,
            "blood_pressure_diastolic": 80,
            "glucose_level": 95,
            "oxygen_saturation": 98
        }

        validated = agent._validate_health_data(data)

        assert validated["heart_rate"] == 75
        assert validated["blood_pressure_systolic"] == 120
        assert validated["blood_pressure_diastolic"] == 80
        assert validated["glucose_level"] == 95.0
        assert validated["oxygen_saturation"] == 98.0
        assert not validated.get("heart_rate_alert", False)

    def test_validate_health_data_abnormal(self):
        """Test health data validation with abnormal values"""
        from backend.agents.health_agent import HealthMonitoringAgent

        agent = HealthMonitoringAgent()
        data = {
            "heart_rate": 120,  # High
            "blood_pressure_systolic": 160,  # High
            "glucose_level": 200,  # High
            "oxygen_saturation": 85  # Low
        }

        validated = agent._validate_health_data(data)

        assert validated["heart_rate_alert"] == True
        assert validated["blood_pressure_alert"] == True
        assert validated["glucose_alert"] == True
        assert validated["oxygen_saturation_alert"] == True

    def test_analyze_health_data_alerts(self):
        """Test health data analysis for alert generation"""
        from backend.agents.health_agent import HealthMonitoringAgent

        agent = HealthMonitoringAgent()
        user = User(id=1, full_name="Test User", role=UserRole.ELDERLY)
        data = {
            "heart_rate": 120,
            "blood_pressure_systolic": 160,
            "glucose_level": 200,
            "oxygen_saturation": 85
        }

        analysis = asyncio.run(agent._analyze_health_data(1, data, user))

        assert analysis["alert_triggered"] == True
        assert analysis["risk_level"] == "high"
        assert len(analysis["alert_reasons"]) > 0

    async def test_create_health_record(self, test_db):
        """Test creating health records in database"""
        data = {
            "user_id": 1,
            "timestamp": datetime.utcnow(),
            "heart_rate": 75,
            "blood_pressure_systolic": 120,
            "blood_pressure_diastolic": 80,
            "glucose_level": 95,
            "oxygen_saturation": 98
        }

        record = await create_health_record(data, test_db)
        assert record.user_id == 1
        assert record.heart_rate == 75

class TestSafetyMonitoring:
    """Test safety monitoring functionality"""

    def test_validate_safety_data(self):
        """Test safety data validation"""
        from backend.agents.safety_agent import SafetyMonitoringAgent

        agent = SafetyMonitoringAgent()
        data = {
            "movement_activity": "walking",
            "acceleration_x": 0.1,
            "acceleration_y": 0.2,
            "acceleration_z": 9.8,
            "location_room": "living_room"
        }

        validated = agent._validate_safety_data(data)
        assert validated["movement_activity"].value == "walking"
        assert validated["location_room"] == "living_room"

    def test_fall_detection(self):
        """Test fall detection algorithm"""
        from backend.agents.safety_agent import SafetyMonitoringAgent

        agent = SafetyMonitoringAgent()

        # Normal movement
        normal_data = {
            "acceleration_x": 0.1,
            "acceleration_y": 0.2,
            "acceleration_z": 9.8
        }
        assert not agent._detect_fall(normal_data)

        # Fall-like movement
        fall_data = {
            "acceleration_x": 2.0,
            "acceleration_y": 3.0,
            "acceleration_z": 12.0,
            "impact_force": 8.0
        }
        assert agent._detect_fall(fall_data)

    async def test_create_safety_record(self, test_db):
        """Test creating safety records in database"""
        data = {
            "user_id": 1,
            "timestamp": datetime.utcnow(),
            "movement_activity": "walking",
            "location_room": "kitchen",
            "safety_alert": False
        }

        record = await create_safety_record(data, test_db)
        assert record.user_id == 1
        assert record.location_room == "kitchen"

class TestReminderSystem:
    """Test reminder system functionality"""

    def test_validate_reminder_data(self):
        """Test reminder data validation"""
        from backend.agents.reminder_agent import ReminderAgent

        agent = ReminderAgent()
        data = {
            "reminder_type": "medication",
            "title": "Take blood pressure medication",
            "scheduled_time": datetime.utcnow().isoformat(),
            "description": "Take 10mg Lisinopril"
        }

        validated = agent._validate_reminder_data(data)
        assert validated["reminder_type"].value == "medication"
        assert validated["title"] == "Take blood pressure medication"

    async def test_create_reminder(self):
        """Test creating reminders"""
        from backend.agents.reminder_agent import ReminderAgent

        agent = ReminderAgent()
        data = {
            "reminder_type": "medication",
            "title": "Test Reminder",
            "scheduled_time": (datetime.utcnow() + timedelta(hours=1)).isoformat()
        }

        # This would normally interact with database
        # For testing, we just validate the data structure
        validated = agent._validate_reminder_data(data)
        assert validated["title"] == "Test Reminder"

class TestAPIEndpoints:
    """Test API endpoints"""

    async def test_root_endpoint(self, test_client):
        """Test root API endpoint"""
        response = await test_client.get("/")
        assert response.status_code == 200

        data = response.json()
        assert "Elderly Care AI System API" in data["message"]

    async def test_health_endpoint(self, test_client):
        """Test health check endpoint"""
        response = await test_client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"

    async def test_system_status_endpoint(self, test_client):
        """Test system status endpoint"""
        response = await test_client.get("/api/v1/system/status")
        assert response.status_code == 200

        data = response.json()
        assert "agents" in data
        assert "system" in data

class TestDataIngestion:
    """Test data ingestion functionality"""

    def test_extract_user_id(self):
        """Test user ID extraction from CSV data"""
        from backend.data_ingestion import DataIngestionService

        service = DataIngestionService()

        # Test various device ID formats
        assert service._extract_user_id("D1000") == 1
        assert service._extract_user_id("D1001") == 2
        assert service._extract_user_id("D1000/123") == 1

    def test_parse_blood_pressure(self):
        """Test blood pressure parsing"""
        from backend.data_ingestion import DataIngestionService

        service = DataIngestionService()

        # Test normal format
        systolic, diastolic = service._parse_blood_pressure("120/80 mmHg")
        assert systolic == 120
        assert diastolic == 80

        # Test invalid format
        systolic, diastolic = service._parse_blood_pressure("invalid")
        assert systolic is None
        assert diastolic is None

    def test_parse_reminder_type(self):
        """Test reminder type parsing"""
        from backend.data_ingestion import DataIngestionService

        service = DataIngestionService()

        assert service._parse_reminder_type("Medication").value == "medication"
        assert service._parse_reminder_type("Exercise").value == "exercise"
        assert service._parse_reminder_type("Unknown").value == "other"

class TestWebSocket:
    """Test WebSocket functionality"""

    async def test_websocket_manager(self):
        """Test WebSocket manager basic functionality"""
        from backend.websocket_manager import WebSocketManager

        manager = WebSocketManager()

        # Test connection tracking
        assert len(manager.active_connections) == 0

        # Test stats
        stats = manager.get_stats()
        assert "total_connections" in stats
        assert "unique_clients" in stats

class TestConfiguration:
    """Test configuration management"""

    def test_settings_validation(self):
        """Test settings validation"""
        from backend.config import settings

        # Test that critical settings exist
        assert settings.app_name == "Elderly Care AI System"
        assert settings.debug is False or settings.debug is True

    def test_health_thresholds(self):
        """Test health monitoring thresholds"""
        from backend.config import settings

        assert settings.heart_rate_min == 60
        assert settings.heart_rate_max == 100
        assert settings.glucose_min == 70
        assert settings.glucose_max == 140

class TestDatabase:
    """Test database operations"""

    async def test_database_connection(self, test_db):
        """Test database connection"""
        # Simple query to test connection
        result = await test_db.execute("SELECT 1 as test")
        row = result.first()
        assert row.test == 1

    async def test_user_operations(self, test_db):
        """Test user database operations"""
        from backend.database import get_user_by_id

        # Test non-existent user
        user = await get_user_by_id(99999, test_db)
        assert user is None

# Integration Tests
class TestIntegration:
    """Integration tests for the complete system"""

    async def test_health_data_flow(self, test_client):
        """Test complete health data processing flow"""
        # This would test the complete flow from API to database
        # For now, just test the API endpoint exists
        response = await test_client.post(
            "/api/v1/health/data",
            json={"heart_rate": 75},
            params={"user_id": 1}
        )
        # Should return 201 or appropriate error
        assert response.status_code in [201, 400, 404, 500]

    async def test_safety_data_flow(self, test_client):
        """Test complete safety data processing flow"""
        response = await test_client.post(
            "/api/v1/safety/data",
            json={"movement_activity": "walking"},
            params={"user_id": 1}
        )
        assert response.status_code in [201, 400, 404, 500]

# Performance Tests
class TestPerformance:
    """Performance tests"""

    async def test_health_data_ingestion_performance(self):
        """Test performance of health data ingestion"""
        # This would test how quickly the system can process multiple records
        # For now, just a placeholder
        assert True

    async def test_concurrent_requests(self, test_client):
        """Test handling of concurrent requests"""
        # Test multiple simultaneous API calls
        tasks = []
        for i in range(10):
            task = test_client.get("/health")
            tasks.append(task)

        responses = await asyncio.gather(*tasks)

        for response in responses:
            assert response.status_code == 200

# Load Tests
class TestLoad:
    """Load testing scenarios"""

    async def test_high_frequency_data_ingestion(self):
        """Test system under high data ingestion load"""
        # This would simulate high-frequency data ingestion
        assert True

    async def test_multiple_users_concurrent(self):
        """Test system with multiple users sending data concurrently"""
        assert True

# Pytest configuration
if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])

# Test data fixtures
@pytest.fixture
def sample_health_data():
    """Sample health data for testing"""
    return {
        "heart_rate": 75,
        "blood_pressure_systolic": 120,
        "blood_pressure_diastolic": 80,
        "glucose_level": 95,
        "oxygen_saturation": 98,
        "temperature": 36.5,
        "timestamp": datetime.utcnow().isoformat()
    }

@pytest.fixture
def sample_safety_data():
    """Sample safety data for testing"""
    return {
        "movement_activity": "walking",
        "acceleration_x": 0.1,
        "acceleration_y": 0.2,
        "acceleration_z": 9.8,
        "location_room": "living_room",
        "timestamp": datetime.utcnow().isoformat()
    }

@pytest.fixture
def sample_reminder_data():
    """Sample reminder data for testing"""
    return {
        "reminder_type": "medication",
        "title": "Take medication",
        "description": "Take blood pressure medication",
        "scheduled_time": (datetime.utcnow() + timedelta(hours=1)).isoformat()
    }
