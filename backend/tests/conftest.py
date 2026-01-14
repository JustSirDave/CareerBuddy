"""
Pytest configuration and fixtures
Provides test database, mock services, and sample data
"""
import pytest
import os
from unittest.mock import Mock, MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import User, Job, Message, Payment
from app.config import settings

# Set test environment
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"


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
        "template": "template_1",
        "target_role": "Backend Engineer",
        "basics": {
            "name": "John Doe",
            "title": "Backend Engineer",
            "email": "john@example.com",
            "phone": "+1234567890",
            "location": "New York, USA"
        },
        "summary": "Experienced Backend Engineer with 5+ years building scalable systems. Skilled in Python, FastAPI, and PostgreSQL.",
        "skills": ["Python", "FastAPI", "PostgreSQL", "Docker", "Redis"],
        "profiles": [
            {"platform": "LinkedIn", "url": "linkedin.com/in/johndoe"},
            {"platform": "GitHub", "url": "github.com/johndoe"}
        ],
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
        "certifications": [
            {"details": "AWS Certified Solutions Architect"}
        ],
        "projects": [
            {"details": "Open-source contributor to FastAPI framework"}
        ]
    }


@pytest.fixture
def sample_cv_data():
    """Sample complete CV data"""
    return {
        "_step": "done",
        "template": "template_1",
        "basics": {
            "name": "Jane Smith",
            "title": "Data Scientist",
            "email": "jane@example.com",
            "phone": "+1987654321",
            "location": "London, UK"
        },
        "summary": "Data Scientist with expertise in machine learning and statistical analysis.",
        "skills": ["Python", "Machine Learning", "TensorFlow", "SQL"],
        "experiences": [
            {
                "role": "Data Scientist",
                "company": "DataCorp",
                "location": "London",
                "start": "Mar 2019",
                "end": "Present",
                "bullets": ["Built ML models with 95% accuracy"]
            }
        ],
        "education": [
            {"details": "PhD in Computer Science, Oxford, 2019"}
        ]
    }


@pytest.fixture
def sample_cover_letter_data():
    """Sample complete cover letter data"""
    return {
        "_step": "done",
        "basics": {
            "name": "Alex Johnson",
            "email": "alex@example.com",
            "phone": "+1234567890",
            "location": "Boston, MA"
        },
        "cover_role": "Senior Product Manager",
        "cover_company": "TechGiant Inc",
        "target_role": "Senior Product Manager",
        "years_experience": "8 years",
        "industries": "SaaS and Enterprise Software",
        "interest_reason": "Your company's focus on AI-driven products aligns with my passion",
        "current_role": "Product Manager at InnovateCo",
        "achievements": "Led product launch that generated $5M ARR in first year",
        "key_skills": "Product strategy, stakeholder management, data-driven decision making",
        "company_goal": "Drive product innovation and deliver exceptional user experiences"
    }


@pytest.fixture
def mock_ai_service():
    """Mock AI service responses"""
    mock = Mock()
    mock.generate_skills.return_value = ["Python", "FastAPI", "PostgreSQL", "Docker", "AWS"]
    mock.generate_summary.return_value = "Experienced professional with proven track record."
    return mock


@pytest.fixture
def mock_telegram_service():
    """Mock Telegram service"""
    mock = Mock()
    mock.send_message.return_value = {"ok": True, "result": {"message_id": 123}}
    mock.send_document.return_value = {"ok": True}
    return mock


@pytest.fixture
def pro_user(db_session):
    """Create test user with pro tier"""
    user = User(
        telegram_user_id="987654321",
        telegram_username="pro_user",
        name="Pro User",
        tier="pro",
        generation_count=0
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def payment_record(db_session, test_user, test_job):
    """Create test payment record"""
    payment = Payment(
        user_id=test_user.id,
        job_id=test_job.id,
        amount=750,
        currency="NGN",
        status="success",
        provider="paystack",
        reference="TEST_REF_123"
    )
    db_session.add(payment)
    db_session.commit()
    db_session.refresh(payment)
    return payment


@pytest.fixture
def mock_pdf_renderer():
    """Mock PDF renderer"""
    mock = Mock()
    mock.render_template_1_pdf.return_value = b"PDF_CONTENT"
    mock.render_template_2_pdf.return_value = b"PDF_CONTENT"
    mock.render_template_3_pdf.return_value = b"PDF_CONTENT"
    return mock


@pytest.fixture
def mock_storage():
    """Mock storage service"""
    mock = Mock()
    mock.save_file_locally.return_value = "/path/to/file.docx"
    mock.convert_docx_to_pdf.return_value = "/path/to/file.pdf"
    return mock
