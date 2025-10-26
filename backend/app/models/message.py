from sqlalchemy import Column, String, DateTime, func, ForeignKey, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID
import uuid
from .base import Base

class Message(Base):
    __tablename__ = "messages"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=True)
    direction = Column(String, nullable=False)  # inbound|outbound
    content = Column(Text, nullable=False)
    wa_id = Column(String, nullable=True)      # WhatsApp message id (optional)
    delivered = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
