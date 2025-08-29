# Users API Router

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.security import HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from ..database import get_db, get_user_by_id, get_user_by_device_id
from ..models import User, UserRole, CaregiverElderlyMapping
from ..config import settings

router = APIRouter()
security = HTTPBearer()
logger = logging.getLogger(__name__)

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: Dict[str, Any],
    db: AsyncSession = Depends(get_db)
):
    """Create a new user"""
    try:
        # Validate required fields
        required_fields = ["device_id", "full_name", "role"]
        for field in required_fields:
            if field not in user_data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Missing required field: {field}"
                )

        # Validate role
        try:
            role = UserRole(user_data["role"])
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid role: {user_data['role']}"
            )

        # Check if device_id already exists
        existing_user = await get_user_by_device_id(user_data["device_id"], db)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Device ID {user_data['device_id']} already exists"
            )

        # Create user
        user = User(
            device_id=user_data["device_id"],
            email=user_data.get("email"),
            phone=user_data.get("phone"),
            full_name=user_data["full_name"],
            role=role,
            date_of_birth=user_data.get("date_of_birth"),
            address=user_data.get("address"),
            medical_conditions=user_data.get("medical_conditions", []),
            allergies=user_data.get("allergies", []),
            medications=user_data.get("medications", []),
            emergency_contacts=user_data.get("emergency_contacts", [])
        )

        db.add(user)
        await db.commit()
        await db.refresh(user)

        return {
            "message": "User created successfully",
            "user_id": user.id,
            "device_id": user.device_id,
            "role": user.role.value,
            "created_at": user.created_at.isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user"
        )

@router.get("/{user_id}")
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get user information"""
    try:
        user = await get_user_by_id(user_id, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )

        return {
            "user_id": user.id,
            "device_id": user.device_id,
            "email": user.email,
            "phone": user.phone,
            "full_name": user.full_name,
            "role": user.role.value,
            "is_active": user.is_active,
            "emergency_contact": user.emergency_contact,
            "date_of_birth": user.date_of_birth.isoformat() if user.date_of_birth else None,
            "address": user.address,
            "medical_conditions": user.medical_conditions,
            "allergies": user.allergies,
            "medications": user.medications,
            "emergency_contacts": user.emergency_contacts,
            "created_at": user.created_at.isoformat(),
            "updated_at": user.updated_at.isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user"
        )

@router.get("/device/{device_id}")
async def get_user_by_device(
    device_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get user information by device ID"""
    try:
        user = await get_user_by_device_id(device_id, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with device ID {device_id} not found"
            )

        return {
            "user_id": user.id,
            "device_id": user.device_id,
            "email": user.email,
            "phone": user.phone,
            "full_name": user.full_name,
            "role": user.role.value,
            "is_active": user.is_active,
            "emergency_contact": user.emergency_contact,
            "date_of_birth": user.date_of_birth.isoformat() if user.date_of_birth else None,
            "address": user.address,
            "medical_conditions": user.medical_conditions,
            "allergies": user.allergies,
            "medications": user.medications,
            "emergency_contacts": user.emergency_contacts,
            "created_at": user.created_at.isoformat(),
            "updated_at": user.updated_at.isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving user by device: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user"
        )

@router.put("/{user_id}")
async def update_user(
    user_id: int,
    update_data: Dict[str, Any],
    db: AsyncSession = Depends(get_db)
):
    """Update user information"""
    try:
        user = await get_user_by_id(user_id, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )

        # Update allowed fields
        allowed_fields = [
            "email", "phone", "full_name", "is_active", "emergency_contact",
            "date_of_birth", "address", "medical_conditions", "allergies",
            "medications", "emergency_contacts"
        ]

        for field in allowed_fields:
            if field in update_data:
                setattr(user, field, update_data[field])

        user.updated_at = datetime.utcnow()

        await db.commit()

        return {
            "message": "User updated successfully",
            "user_id": user_id,
            "updated_at": user.updated_at.isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user"
        )

@router.get("/")
async def list_users(
    role: Optional[str] = Query(None, description="Filter by role"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    limit: int = Query(50, description="Number of users to retrieve", ge=1, le=500),
    offset: int = Query(0, description="Number of users to skip", ge=0),
    db: AsyncSession = Depends(get_db)
):
    """List users with optional filtering"""
    try:
        from sqlalchemy import select

        query = select(User)

        # Apply filters
        if role:
            try:
                role_enum = UserRole(role)
                query = query.where(User.role == role_enum)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid role: {role}"
                )

        if is_active is not None:
            query = query.where(User.is_active == is_active)

        # Execute query
        result = await db.execute(
            query.order_by(User.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        users = result.scalars().all()

        # Convert to response format
        user_list = []
        for user in users:
            user_list.append({
                "user_id": user.id,
                "device_id": user.device_id,
                "email": user.email,
                "phone": user.phone,
                "full_name": user.full_name,
                "role": user.role.value,
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat()
            })

        return {
            "total_users": len(user_list),
            "users": user_list,
            "offset": offset,
            "limit": limit
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing users: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list users"
        )

@router.post("/{caregiver_id}/assign-elderly/{elderly_id}")
async def assign_elderly_to_caregiver(
    caregiver_id: int,
    elderly_id: int,
    assignment_data: Dict[str, Any] = None,
    db: AsyncSession = Depends(get_db)
):
    """Assign an elderly person to a caregiver"""
    try:
        if assignment_data is None:
            assignment_data = {}

        # Validate users exist
        caregiver = await get_user_by_id(caregiver_id, db)
        if not caregiver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Caregiver {caregiver_id} not found"
            )

        elderly = await get_user_by_id(elderly_id, db)
        if not elderly:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Elderly user {elderly_id} not found"
            )

        # Validate roles
        if caregiver.role not in [UserRole.CAREGIVER, UserRole.HEALTHCARE_PROVIDER]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is not a caregiver or healthcare provider"
            )

        if elderly.role != UserRole.ELDERLY:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is not an elderly person"
            )

        # Check if assignment already exists
        from sqlalchemy import select
        result = await db.execute(
            select(CaregiverElderlyMapping).where(
                CaregiverElderlyMapping.caregiver_id == caregiver_id,
                CaregiverElderlyMapping.elderly_id == elderly_id
            )
        )
        existing_mapping = result.scalar_one_or_none()

        if existing_mapping:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Assignment already exists"
            )

        # Create assignment
        mapping = CaregiverElderlyMapping(
            caregiver_id=caregiver_id,
            elderly_id=elderly_id,
            relationship_type=assignment_data.get("relationship_type", "professional"),
            notification_preferences=assignment_data.get("notification_preferences", {}),
            is_primary_caregiver=assignment_data.get("is_primary_caregiver", False)
        )

        db.add(mapping)
        await db.commit()

        return {
            "message": "Elderly person assigned to caregiver successfully",
            "caregiver_id": caregiver_id,
            "elderly_id": elderly_id,
            "relationship_type": mapping.relationship_type,
            "is_primary_caregiver": mapping.is_primary_caregiver
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error assigning elderly to caregiver: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to assign elderly to caregiver"
        )

@router.get("/{caregiver_id}/elderly")
async def get_caregiver_elderly(
    caregiver_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get elderly persons assigned to a caregiver"""
    try:
        # Validate caregiver exists
        caregiver = await get_user_by_id(caregiver_id, db)
        if not caregiver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Caregiver {caregiver_id} not found"
            )

        # Get assignments
        from sqlalchemy import select
        result = await db.execute(
            select(CaregiverElderlyMapping, User)
            .join(User, CaregiverElderlyMapping.elderly_id == User.id)
            .where(CaregiverElderlyMapping.caregiver_id == caregiver_id)
        )

        assignments = []
        for mapping, elderly in result:
            assignments.append({
                "elderly_id": elderly.id,
                "device_id": elderly.device_id,
                "full_name": elderly.full_name,
                "relationship_type": mapping.relationship_type,
                "is_primary_caregiver": mapping.is_primary_caregiver,
                "notification_preferences": mapping.notification_preferences,
                "assigned_at": mapping.created_at.isoformat()
            })

        return {
            "caregiver_id": caregiver_id,
            "total_assignments": len(assignments),
            "assignments": assignments
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving caregiver assignments: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve caregiver assignments"
        )

@router.get("/roles")
async def get_user_roles():
    """Get available user roles"""
    return {
        "roles": [
            {
                "value": role.value,
                "label": role.value.replace("_", " ").title(),
                "description": _get_role_description(role)
            }
            for role in UserRole
        ]
    }

def _get_role_description(role: UserRole) -> str:
    """Get description for user role"""
    descriptions = {
        UserRole.ELDERLY: "Elderly individual receiving care and monitoring",
        UserRole.CAREGIVER: "Family member or professional caregiver",
        UserRole.HEALTHCARE_PROVIDER: "Medical professional providing healthcare services",
        UserRole.ADMIN: "System administrator with full access"
    }
    return descriptions.get(role, "Unknown role")
