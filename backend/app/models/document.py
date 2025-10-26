from sqlalchemy import Column, String, DateTime, func, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid
from .base import Base

class Document(Base):
    __tablename__ = "documents"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    type = Column(String, nullable=False)  # resume|cv|cover_letter
    template = Column(String)
    profile_snapshot = Column(JSONB)
    file_urls = Column(JSONB)  # {"pdf": "...", "docx": "..."}
    created_at = Column(DateTime(timezone=True), server_default=func.now())
