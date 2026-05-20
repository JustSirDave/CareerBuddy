"""
CareerBuddy — AI Career Document Assistant
Copyright (C) 2026 Xenaptis Technologies
Licensed under AGPL-3.0: https://www.gnu.org/licenses/agpl-3.0.html
"""
from sqlalchemy import Column, String, DateTime, Boolean, Integer, Date
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db import Base
import uuid


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    telegram_user_id = Column(String(50), unique=True, nullable=False, index=True)
    telegram_username = Column(String(100))
    telegram_first_name = Column(String(100), nullable=True)
    name = Column(String(200))
    email = Column(String(200))
    phone = Column(String(50))
    locale = Column(String(10), default="en")

    # Monthly usage limit
    monthly_doc_count = Column(Integer, default=0, nullable=False, server_default="0")
    monthly_reset_date = Column(Date, nullable=True)

    onboarding_complete = Column(Boolean, default=False, nullable=False)
    onboarding_step = Column(String(50), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    jobs = relationship("Job", back_populates="user", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="user", cascade="all, delete-orphan")
    feedback = relationship("Feedback", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, telegram_user_id={self.telegram_user_id}, name={self.name})>"
