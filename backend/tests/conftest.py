"""
Pytest configuration and fixtures
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import User, Job, Message


@pytest.fixture
def db_engine():
    """Create in-memory SQLite database for testing"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session(db_engine):
    """Create database session for testing"""
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_user(db_session):
    """Create test user"""
    user = User(
        telegram_user_id="123456789",
        telegram_username="test_user",
        name="Test User",
        email="test@example.com",
        phone="+1234567890"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_job(db_session, test_user):
    """Create test job"""
    job = Job(
        user_id=test_user.id,
        type="resume",
        status="collecting",
        answers={"_step": "basics"}
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


@pytest.fixture
def sample_resume_data():
    """Sample complete resume data"""
    return {
        "_step": "done",
        "basics": {
            "name": "John Doe",
            "title": "Backend Engineer",
            "email": "john@example.com",
            "phone": "+1234567890",
            "location": "New York, USA"
        },
        "summary": "Experienced Backend Engineer with 5+ years building scalable systems. Skilled in Python, FastAPI, and PostgreSQL.",
        "skills": ["Python", "FastAPI", "PostgreSQL", "Docker", "Redis"],
        "experiences": [
            {
                "role": "Senior Backend Engineer",
                "company": "TechCorp",
                "location": "NYC",
                "start": "Jan 2020",
                "end": "Present",
                "bullets": [
                    "Built API serving 1M+ requests/day with 99.9% uptime",
                    "Reduced database query time by 60% through optimization",
                    "Led team of 3 engineers in microservices migration"
                ]
            },
            {
                "role": "Backend Engineer",
                "company": "StartupCo",
                "location": "SF",
                "start": "Jun 2018",
                "end": "Dec 2019",
                "bullets": [
                    "Developed core API using Python and PostgreSQL",
                    "Implemented caching layer with Redis"
                ]
            }
        ],
        "education": [
            {"details": "B.Sc. Computer Science, MIT, 2018"}
        ],
        "projects": [
            {"details": "Open-source contributor to FastAPI framework"}
        ]
    }
