"""
File model for S3/R2 cloud storage integration.

NOTE: This model is implemented but NOT YET INTEGRATED into the application workflow.
Currently, documents are stored locally on the filesystem.
This model is ready for future cloud storage migration.

To integrate:
1. Call storage.upload_file() after document generation
2. Store storage_key in this table
3. Use storage.get_download_url() for serving files
"""
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