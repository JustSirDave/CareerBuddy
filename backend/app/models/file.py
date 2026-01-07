from sqlalchemy import Column, String, DateTime, Integer, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db import Base
import uuid


class File(Base):
    __tablename__ = "files"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)

    kind = Column(String(50), nullable=False)  # preview_pdf, final_pdf, final_docx
    storage_key = Column(String(500), nullable=False)  # S3/R2 object key
    checksum = Column(String(64))  # SHA256 hash
    size = Column(Integer)  # Size in bytes

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    job = relationship("Job", back_populates="files")

    def __repr__(self):
        return f"<File(id={self.id}, kind={self.kind}, storage_key={self.storage_key})>"