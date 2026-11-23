from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, JSON
from sqlalchemy.orm import relationship
from app.db.session import Base
from app.models.base import TimestampMixin, generate_uuid
from app.core.rbac_constants import get_role_definition


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(150), nullable=False)
    phone = Column(String(30), nullable=True)

    # Role definition (code-level constant with optional database role pointer)
    role_id = Column(String(36), ForeignKey("roles.id", ondelete="SET NULL"), nullable=True, index=True)
    role_slug = Column(String(50), default="super_admin", nullable=False)

    # Multi-branch assignment (Super Admin does not require a branch to log in)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True)

    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    must_change_password = Column(Boolean, default=False, nullable=False)
    last_login = Column(DateTime(timezone=True), nullable=True)
    preferences = Column(JSON, default=dict, nullable=False)

    # Relationships
    role = relationship("Role", back_populates="users", foreign_keys=[role_id], lazy="joined")
    branch = relationship("Branch", back_populates="users", lazy="joined")

    @property
    def effective_role(self):
        if self.role is not None:
            return self.role
        return get_role_definition(self.role_slug)
