# AI for Elderly Care and Support

A comprehensive multi-agentic AI system designed to provide real-time monitoring, reminders, and safety alerts for elderly individuals living independently. The system integrates health monitoring, safety tracking, and daily activity reminders to ensure optimal care and peace of mind for both elderly users and their caregivers.

## Features

### 🏥 Health Monitoring Agent
- Real-time vital signs monitoring (heart rate, blood pressure, glucose levels, oxygen saturation)
- Automated threshold detection and alerts
- Predictive health insights using machine learning
- Historical health data analysis

### 🛡️ Safety Monitoring Agent
- Fall detection using accelerometer data
- Movement activity tracking
- Location monitoring
- Emergency alert system with caregiver notifications

### 📅 Reminder Agent
- Medication schedule management
- Appointment reminders
- Daily activity scheduling
- Voice note notifications
- Acknowledgment tracking

### 🚨 Alert System
- Multi-channel notifications (SMS, email, push notifications)
- Emergency response coordination
- Caregiver notification system
- Real-time alert dashboard

### 📊 Caregiver Dashboard
- Real-time monitoring interface
- Historical data visualization
- Alert management system
- User management and settings

## Architecture

The system uses a multi-agent architecture with the following components:

- **Backend**: FastAPI with PostgreSQL database
- **Frontend**: React.js with real-time WebSocket updates
- **Agents**: Python-based agents using CrewAI framework
- **ML Models**: Free open-source models for health predictions
- **Real-time Processing**: Redis for message queuing and WebSockets
- **Deployment**: Docker containerization for scalability

## Installation

### Prerequisites
- Python 3.9+
- Node.js 16+
- PostgreSQL
- Redis
- Docker (optional)

### Backend Setup
```bash
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --reload
```

### Frontend Setup
```bash
cd frontend
npm install
npm start
```

### Database Setup
```bash
cd database
docker-compose up -d
```

## Usage

1. **Configure Devices**: Set up wearable devices for health and safety monitoring
2. **Register Users**: Add elderly users and their caregivers to the system
3. **Set Thresholds**: Configure health parameter thresholds for alerts
4. **Schedule Reminders**: Set up medication and activity reminders
5. **Monitor Dashboard**: Use the caregiver dashboard for real-time monitoring

## API Documentation

The system provides RESTful APIs for:
- User management
- Health data ingestion
- Safety monitoring
- Reminder management
- Alert configuration

API documentation is available at `/docs` when the backend is running.

## Security Features

- End-to-end encryption for health data
- Role-based access control
- Secure API authentication
- HIPAA-compliant data handling
- Privacy-preserving ML models

## Scalability

- Horizontal scaling with Docker containers
- Database sharding for large datasets
- Redis caching for performance
- Load balancing for high availability

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Built for Accenture Hackathon - AI for Elderly Care
- Uses open-source technologies and free ML models
- Designed for real-world deployment and scalability
