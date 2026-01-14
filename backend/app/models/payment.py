"""
CareerBuddy - Payment Model
Author: Sir Dave
"""
from sqlalchemy import Column, String, DateTime, Integer, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db import Base
import uuid


class Payment(Base):
    __tablename__ = "payments"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id = Column(String, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True)

    provider = Column(String(50), default="paystack")
    amount = Column(Integer, nullable=False)  # Amount in kobo (NGN) or smallest currency unit
    currency = Column(String(10), default="NGN")
    status = Column(String(50), default="init")  # init, success, failed, refunded
    reference = Column(String(200), unique=True, index=True)  # Paystack reference

    payment_metadata = Column(JSON)  # Sanitized metadata from provider
    raw_webhook = Column(JSON)  # Store full webhook payload for debugging

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="payments")
    job = relationship("Job", back_populates="payments")

    def __repr__(self):
        return f"<Payment(id={self.id}, reference={self.reference}, status={self.status})>"