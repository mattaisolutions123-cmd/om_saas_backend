from sqlalchemy import Column, String, Float, Integer, Boolean, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.models.base import TimestampMixin, generate_uuid
from app.db.session import Base


class Supplier(Base, TimestampMixin):
    """
    Vendor or parts supplier with GSTIN, commercial credit terms, and bank details.
    """
    __tablename__ = "suppliers"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=True)

    name = Column(String(200), nullable=False)
    supplier_type = Column(String(30), nullable=False, default="legal_entity")  # individual, legal_entity
    contact_name = Column(String(100), nullable=True)
    phone = Column(String(30), nullable=False)
    email = Column(String(100), nullable=True)

    gstin = Column(String(25), nullable=True)
    pan = Column(String(20), nullable=True)
    credit_period_days = Column(Integer, nullable=False, default=30)  # e.g. 0, 15, 30, 45, 60 days
    credit_limit = Column(Float, nullable=False, default=0.0)
    payment_terms = Column(String(100), nullable=False, default="Net 30")

    address = Column(String(255), nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    state_code = Column(String(10), nullable=True)
    pincode = Column(String(20), nullable=True)

    # Bank details JSON {account_number, ifsc, bank_name, branch_name}
    bank_details = Column(JSON, nullable=False, default=dict)
    rating = Column(Float, nullable=False, default=5.0)  # 1.0 to 5.0
    tags = Column(JSON, nullable=False, default=list)  # ["OEM", "Wholesale", "Batteries"]
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    branch = relationship("Branch", backref="suppliers")
