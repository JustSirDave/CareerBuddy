from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings

# e.g., postgresql+psycopg://postgres:postgres@postgres:5432/buddy
DATABASE_URL = settings.__dict__.get("DATABASE_URL") or \
               "postgresql+psycopg://postgres:postgres@postgres:5432/buddy"

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
