from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db import Base
import uuid


class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id = Column(String, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True)

    direction = Column(String(20), nullable=False)  # inbound, outbound
    content = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="messages")
    job = relationship("Job", back_populates="messages")

    def __repr__(self):
        return f"<Message(id={self.id}, direction={self.direction})>"