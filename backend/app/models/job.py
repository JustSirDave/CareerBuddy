
from sqlalchemy import Column, String, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db import Base
import uuid


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String(50), nullable=False)  # resume, cv, cover_letter
    status = Column(String(50), default="collecting", index=True)
    # Status flow: collecting → draft_ready → preview_ready → awaiting_payment → paid → rendering → delivered → closed

    answers = Column(JSON, default=dict)  # Stores conversation state + user answers
    draft_text = Column(String)  # Generated draft
    final_text = Column(String)  # Processed final version

    last_msg_id = Column(String(255), index=True)  # Telegram message deduplication

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="jobs")
    messages = relationship("Message", back_populates="job", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="job", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Job(id={self.id}, type={self.type}, status={self.status})>"