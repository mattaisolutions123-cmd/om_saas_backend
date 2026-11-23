"""
Phase 9 Database Initializer
Creates the scheduled_reports table in omnisuite.db.
"""
from sqlalchemy import create_engine
from app.db.session import Base
import app.models

def init_phase9_db():
    sync_url = "sqlite:///d:/om_spare_saas/omnisuite/backend/omnisuite.db"
    engine = create_engine(sync_url)
    Base.metadata.create_all(bind=engine)
    print("✅ Phase 9 Database Tables Initialized Successfully.")

if __name__ == "__main__":
    init_phase9_db()
