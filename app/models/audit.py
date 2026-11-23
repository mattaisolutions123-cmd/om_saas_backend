from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, String, JSON
from app.db.session import Base
from app.models.base import generate_uuid, utc_now


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    actor_id = Column(String(36), nullable=True, index=True)
    actor_name = Column(String(150), nullable=True)
    actor_email = Column(String(255), nullable=True)
    actor_role = Column(String(100), nullable=True)
    branch_id = Column(String(36), nullable=True, index=True)
    
    action = Column(String(100), nullable=False, index=True)  # CREATE, UPDATE, DELETE, STATUS_CHANGE, PAYMENT, STOCK_MOVE, PRICE_EDIT, LOGIN, LOGOUT
    entity = Column(String(100), nullable=False, index=True)  # User, Ticket, Payment, Invoice, Stock, Cashbox
    entity_id = Column(String(500), nullable=True, index=True)
    
    before_state = Column(JSON, nullable=True)
    after_state = Column(JSON, nullable=True)
    
    ip_address = Column(String(60), nullable=True)
    user_agent = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
