"""Legacy seed script entrypoint - redirects to idempotent admin bootstrap."""
import asyncio
from app.scripts.seed_admin import seed_admin_user

if __name__ == "__main__":
    asyncio.run(seed_admin_user())
