# ============================================================================
# FILE: backend/app/models/user.py
# ============================================================================

from sqlalchemy import Column, String, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db import Base
import uuid


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    telegram_user_id = Column(String(50), unique=True, nullable=False, index=True)  # Telegram chat ID
    telegram_username = Column(String(100))  # Optional Telegram username
    name = Column(String(200))
    email = Column(String(200))
    phone = Column(String(50))
    locale = Column(String(10), default="en")
    tier = Column(String(20), default="free", nullable=False)  # free or pro
    generation_count = Column(String, default="{}", nullable=False)  # JSON: {role_name: count}
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    jobs = relationship("Job", back_populates="user", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="user", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, telegram_user_id={self.telegram_user_id}, name={self.name})>"