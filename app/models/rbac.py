from sqlalchemy import Boolean, Column, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from app.db.session import Base
from app.models.base import TimestampMixin, generate_uuid


class Role(Base, TimestampMixin):
    __tablename__ = "roles"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(100), unique=True, nullable=False, index=True)
    slug = Column(String(100), unique=True, nullable=False, index=True)  # owner, branch_manager, cashier, technician
    description = Column(Text, nullable=True)
    is_system = Column(Boolean, default=False, nullable=False)

    # Relationships
    permissions = relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")
    users = relationship("User", back_populates="role")


class Permission(Base, TimestampMixin):
    __tablename__ = "permissions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    code = Column(String(100), unique=True, nullable=False, index=True)  # e.g., tickets:create, inventory:view
    module = Column(String(50), nullable=False, index=True)  # tickets, inventory, etc.
    description = Column(Text, nullable=True)


class RolePermission(Base, TimestampMixin):
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "module", name="uq_role_permission_module"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    role_id = Column(String(36), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)
    module = Column(String(50), nullable=False, index=True)  # trends, tickets, payments, etc.
    access_level = Column(String(50), nullable=False)  # FULL, BRANCH, VIEW_ONLY, ASSIGNED_ONLY, NONE, etc.

    role = relationship("Role", back_populates="permissions")
