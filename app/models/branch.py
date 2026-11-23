from sqlalchemy import Boolean, Column, String, Text, JSON
from sqlalchemy.orm import relationship
from app.db.session import Base
from app.models.base import TimestampMixin, generate_uuid


class Branch(Base, TimestampMixin):
    __tablename__ = "branches"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(150), nullable=False)
    code = Column(String(50), unique=True, nullable=False, index=True)
    phone = Column(String(30), nullable=True)
    email = Column(String(100), nullable=True)
    address_line = Column(Text, nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    pincode = Column(String(20), nullable=True)
    state_code = Column(String(10), nullable=True)  # GST state code e.g. "27" for MH
    gstin = Column(String(25), nullable=True)
    currency = Column(String(10), default="INR", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    settings = Column(JSON, default=dict, nullable=False)  # Branch specific preferences/metadata

    # Relationships
    users = relationship("User", back_populates="branch", cascade="all, delete-orphan")
