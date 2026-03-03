"""
CareerBuddy - User Model
Author: Sir Dave
"""
from sqlalchemy import Column, String, DateTime, Boolean, Integer
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

    # Credit-based access (replaces old tier/quota system)
    free_resume_used = Column(Boolean, default=False, nullable=False)
    free_cover_letter_used = Column(Boolean, default=False, nullable=False)
    document_credits = Column(Integer, default=0, nullable=False)
    cover_letter_credits = Column(Integer, default=0, nullable=False)

    onboarding_complete = Column(Boolean, default=False, nullable=False)
    onboarding_step = Column(String(50), nullable=True)

    # Referral system
    referral_credits = Column(Integer, default=0, nullable=False)
    referred_by_code = Column(String(20), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    jobs = relationship("Job", back_populates="user", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="user", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, telegram_user_id={self.telegram_user_id}, name={self.name})>"