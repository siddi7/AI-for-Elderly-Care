# Database Configuration and Session Management

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from contextlib import asynccontextmanager
import logging
from typing import AsyncGenerator
from .config import settings
from .models import Base

logger = logging.getLogger(__name__)

# Create async engine
engine = create_async_engine(
    settings.database_url.replace("postgresql://", "postgresql+asyncpg://"),
    echo=settings.debug,
    poolclass=NullPool,
)

# Create async session factory
async_session_factory = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def init_db() -> None:
    """Initialize database and create tables"""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

async def close_db() -> None:
    """Close database connections"""
    try:
        await engine.dispose()
        logger.info("Database connections closed")
    except Exception as e:
        logger.error(f"Failed to close database: {e}")

@asynccontextmanager
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session"""
    session = async_session_factory()
    try:
        yield session
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.error(f"Database session error: {e}")
        raise
    finally:
        await session.close()

# Health check for database
async def health_check() -> dict:
    """Database health check"""
    try:
        async with engine.begin() as conn:
            await conn.execute("SELECT 1")
        return {"status": "healthy", "message": "Database connection successful"}
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {"status": "unhealthy", "message": str(e)}

# Database utility functions
async def get_user_by_device_id(device_id: str, session: AsyncSession) -> Optional[User]:
    """Get user by device ID"""
    from .models import User
    result = await session.execute(
        select(User).where(User.device_id == device_id)
    )
    return result.scalar_one_or_none()

async def get_user_by_id(user_id: int, session: AsyncSession) -> Optional[User]:
    """Get user by ID"""
    from .models import User
    result = await session.execute(
        select(User).where(User.id == user_id)
    )
    return result.scalar_one_or_none()

async def create_health_record(data: dict, session: AsyncSession) -> HealthRecord:
    """Create a new health record"""
    from .models import HealthRecord
    record = HealthRecord(**data)
    session.add(record)
    await session.flush()
    return record

async def create_safety_record(data: dict, session: AsyncSession) -> SafetyRecord:
    """Create a new safety record"""
    from .models import SafetyRecord
    record = SafetyRecord(**data)
    session.add(record)
    await session.flush()
    return record

async def get_recent_health_records(user_id: int, limit: int = 100, session: AsyncSession = None) -> List[HealthRecord]:
    """Get recent health records for a user"""
    from .models import HealthRecord
    from sqlalchemy import select

    if session is None:
        async with get_db() as session:
            result = await session.execute(
                select(HealthRecord)
                .where(HealthRecord.user_id == user_id)
                .order_by(HealthRecord.timestamp.desc())
                .limit(limit)
            )
            return result.scalars().all()
    else:
        result = await session.execute(
            select(HealthRecord)
            .where(HealthRecord.user_id == user_id)
            .order_by(HealthRecord.timestamp.desc())
            .limit(limit)
        )
        return result.scalars().all()

async def get_recent_safety_records(user_id: int, limit: int = 100, session: AsyncSession = None) -> List[SafetyRecord]:
    """Get recent safety records for a user"""
    from .models import SafetyRecord
    from sqlalchemy import select

    if session is None:
        async with get_db() as session:
            result = await session.execute(
                select(SafetyRecord)
                .where(SafetyRecord.user_id == user_id)
                .order_by(SafetyRecord.timestamp.desc())
                .limit(limit)
            )
            return result.scalars().all()
    else:
        result = await session.execute(
            select(SafetyRecord)
            .where(SafetyRecord.user_id == user_id)
            .order_by(SafetyRecord.timestamp.desc())
            .limit(limit)
        )
        return result.scalars().all()

async def get_pending_reminders(session: AsyncSession) -> List[Reminder]:
    """Get pending reminders that need to be sent"""
    from .models import Reminder
    from datetime import datetime
    from sqlalchemy import select

    result = await session.execute(
        select(Reminder)
        .where(Reminder.scheduled_time <= datetime.utcnow())
        .where(Reminder.is_sent == False)
    )
    return result.scalars().all()

async def get_active_alerts(session: AsyncSession) -> List[Alert]:
    """Get active unresolved alerts"""
    from .models import Alert
    from sqlalchemy import select

    result = await session.execute(
        select(Alert)
        .where(Alert.is_resolved == False)
        .order_by(Alert.created_at.desc())
    )
    return result.scalars().all()

# Import here to avoid circular imports
from .models import User, HealthRecord, SafetyRecord, Reminder, Alert
from typing import List, Optional
