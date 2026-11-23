from sqlalchemy import Column, String, Float, Integer, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.models.base import TimestampMixin, generate_uuid
from app.db.session import Base


class ServiceCatalogItem(Base, TimestampMixin):
    """
    Labor and Service rate card catalog with SAC code, pricing, duration, and warranty.
    """
    __tablename__ = "service_catalog_items"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=True)

    name = Column(String(150), nullable=False)
    category = Column(String(100), nullable=False, default="Repair & Maintenance")
    sac_code = Column(String(20), nullable=False, default="9987")  # SAC code for repair/maintenance
    description = Column(Text, nullable=True)

    labor_price = Column(Float, nullable=False, default=0.0)
    duration_minutes = Column(Integer, nullable=False, default=60)
    gst_rate = Column(Float, nullable=False, default=18.0)  # Standard 18% GST on services
    warranty_days = Column(Integer, nullable=False, default=90)
    commission_rate = Column(Float, nullable=False, default=0.0)  # Technician commission percentage

    is_active = Column(Boolean, nullable=False, default=True)

    # Relationships
    branch = relationship("Branch", backref="service_items")
