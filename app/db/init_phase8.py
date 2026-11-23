"""
Phase 8 Database Initializer
Creates the new tables for Notifications, Opt-Outs, Payment Transactions, Customer Feedback, and Automation.
"""
from sqlalchemy import create_engine
from app.db.session import Base
import app.models  # Ensures all models are registered in Base.metadata

def init_phase8_db():
    sync_url = "sqlite:///d:/om_spare_saas/omnisuite/backend/omnisuite.db"
    engine = create_engine(sync_url)
    Base.metadata.create_all(bind=engine)
    print("✅ Phase 8 Database Tables Initialized Successfully.")

if __name__ == "__main__":
    init_phase8_db()
