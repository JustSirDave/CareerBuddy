"""
CareerBuddy — AI Career Document Assistant
Copyright (C) 2026 Xenaptis Technologies
Licensed under AGPL-3.0: https://www.gnu.org/licenses/agpl-3.0.html
"""
from sqlalchemy import Column, String, DateTime, JSON, ForeignKey, Integer, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db import Base
import uuid


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String(50), nullable=False)  # resume, cv, cover_letter, revamp
    status = Column(String(50), default="collecting", index=True)

    answers = Column(JSON, default=dict)
    draft_text = Column(String)
    final_text = Column(String)

    last_msg_id = Column(String(255), index=True)

    revision_count = Column(Integer, default=0, nullable=False)
    revision_answers = Column(JSON, default=dict)

    completed_at = Column(DateTime(timezone=True), nullable=True)
    delivery_confirmation_sent = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="jobs")
    messages = relationship("Message", back_populates="job", cascade="all, delete-orphan")
    feedback = relationship("Feedback", back_populates="job", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Job(id={self.id}, type={self.type}, status={self.status})>"
