"""
CareerBuddy - Feedback Model
"""
import uuid

from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db import Base


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id = Column(String, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True)

    rating = Column(String(10), nullable=True)   # "good" or "bad"
    feedback_text = Column(Text, nullable=True)  # typed text for "bad" rating

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="feedback")
    job = relationship("Job", back_populates="feedback")

    def __repr__(self):
        return f"<Feedback(id={self.id}, rating={self.rating})>"
