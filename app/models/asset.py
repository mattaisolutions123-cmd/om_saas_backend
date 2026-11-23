from sqlalchemy import Boolean, Column, String, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship
from app.db.session import Base
from app.models.base import TimestampMixin, generate_uuid


class Asset(Base, TimestampMixin):
    __tablename__ = "assets"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    client_id = Column(String(36), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=True, index=True)

    # Asset Name & Classification
    name = Column(String(200), nullable=False, index=True)
    brand = Column(String(100), nullable=True, index=True)
    model = Column(String(100), nullable=True, index=True)
    asset_type = Column(String(50), default="device", nullable=False, index=True)  # mobile, laptop, vehicle, motor, appliance, hvac

    # Unique Identifier: Serial number, IMEI, VIN / Chassis No, Vehicle Reg No
    identifier = Column(String(100), nullable=False, index=True)

    # Dynamic JSONB Attributes (holds specs from CustomFieldDefinitions: e.g. HP rating, SWG wire, odometer, fuel, passcode)
    dynamic_attributes = Column(JSON, default=dict, nullable=False)

    # Warranty Tracking
    warranty_status = Column(String(30), default="none", nullable=False)  # active, expired, extended, none
    warranty_expiry = Column(DateTime(timezone=True), nullable=True)
    purchase_date = Column(DateTime(timezone=True), nullable=True)

    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    client = relationship("Client", back_populates="assets")
    branch = relationship("Branch", foreign_keys=[branch_id])
