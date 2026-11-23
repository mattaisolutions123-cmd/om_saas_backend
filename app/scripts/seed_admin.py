import asyncio
import os
import sys
from pathlib import Path
from sqlalchemy import select

# Ensure backend root is on path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import AsyncSessionLocal
from app.models.user import User


async def seed_admin_user() -> bool:
    """
    Idempotent bootstrap routine.
    Creates exactly ONE super_admin user using ADMIN_EMAIL and ADMIN_PASSWORD from settings.
    If the user already exists, does nothing.
    """
    admin_email = getattr(settings, "ADMIN_EMAIL", "admin@mail.com").strip().lower()
    admin_password = getattr(settings, "ADMIN_PASSWORD", "Mail@4321admin")

    if not admin_email or not admin_password:
        print("[seed_admin] Error: ADMIN_EMAIL or ADMIN_PASSWORD not configured in backend .env")
        return False

    async with AsyncSessionLocal() as db:
        # Check if any user with this email exists
        stmt = select(User).where(User.email == admin_email)
        res = await db.execute(stmt)
        existing_user = res.scalar_one_or_none()

        if existing_user:
            print(f"[seed_admin] Admin user '{admin_email}' already exists. No action required.")
            return False

        # Create the single Super Admin user
        admin = User(
            email=admin_email,
            hashed_password=get_password_hash(admin_password),
            full_name="Super Administrator",
            role_slug="super_admin",
            branch_id=None,  # Zero-branch unrestricted login
            is_active=True,
            is_superuser=True,
            must_change_password=True,
        )
        db.add(admin)
        await db.commit()
        print(f"[seed_admin] Successfully bootstrapped single Super Admin user: {admin_email}")
        return True


def main():
    asyncio.run(seed_admin_user())


if __name__ == "__main__":
    main()
