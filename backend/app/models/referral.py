"""
CareerBuddy - Referral Model
Tracks referral codes and conversions.
"""
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db import Base
import uuid


class Referral(Base):
    __tablename__ = "referrals"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    referrer_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    referee_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    code = Column(String(20), unique=True, nullable=False, index=True)
    status = Column(String(20), default="pending")  # pending | converted | rewarded
    converted_at = Column(DateTime(timezone=True), nullable=True)
    rewarded_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    referrer = relationship("User", foreign_keys=[referrer_id])
    referee = relationship("User", foreign_keys=[referee_id])

    def __repr__(self):
        return f"<Referral(code={self.code}, status={self.status})>"
