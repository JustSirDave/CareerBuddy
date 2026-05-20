"""
Tests for database models
Validates model creation, relationships, and constraints
"""
import pytest
from sqlalchemy.exc import IntegrityError
from app.models import User, Job, Message


class TestUserModel:
    """Test User model"""

    def test_create_user(self, db_session):
        """Test creating a basic user"""
        user = User(
            telegram_user_id="111222333",
            telegram_username="testuser",
            name="Test User"
        )
        db_session.add(user)
        db_session.commit()
        
        assert user.id is not None
        assert user.telegram_user_id == "111222333"

    def test_user_telegram_id_unique(self, db_session, test_user):
        """Test telegram_user_id uniqueness constraint"""
        duplicate_user = User(
            telegram_user_id=test_user.telegram_user_id,  # Same ID
            telegram_username="another_user"
        )
        db_session.add(duplicate_user)
        
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_user_relationships(self, db_session, test_user, test_job):
        """Test user has jobs relationship"""
        assert len(test_user.jobs) == 1
        assert test_user.jobs[0].id == test_job.id

    def test_user_cascade_delete(self, db_session, test_user, test_job):
        """Test deleting user cascades to jobs"""
        user_id = test_user.id
        job_id = test_job.id
        
        db_session.delete(test_user)
        db_session.commit()
        
        # Job should be deleted
        assert db_session.query(Job).filter(Job.id == job_id).first() is None
        assert db_session.query(User).filter(User.id == user_id).first() is None


class TestJobModel:
    """Test Job model"""

    def test_create_job(self, db_session, test_user):
        """Test creating a job"""
        job = Job(
            user_id=test_user.id,
            type="resume",
            status="collecting",
            answers={"_step": "basics"}
        )
        db_session.add(job)
        db_session.commit()
        
        assert job.id is not None
        assert job.type == "resume"
        assert job.status == "collecting"
        assert job.answers["_step"] == "basics"

    def test_job_types(self, db_session, test_user):
        """Test different job types"""
        for job_type in ["resume", "cv", "cover"]:
            job = Job(user_id=test_user.id, type=job_type)
            db_session.add(job)
            db_session.commit()
            assert job.type == job_type
            db_session.delete(job)
            db_session.commit()

    def test_job_status_flow(self, db_session, test_job):
        """Test job status transitions"""
        status_flow = ["collecting", "draft_ready", "preview_ready", "done"]
        
        for status in status_flow:
            test_job.status = status
            db_session.commit()
            db_session.refresh(test_job)
            assert test_job.status == status

    def test_job_answers_json(self, db_session, test_job):
        """Test JSON answers column"""
        test_job.answers = {
            "_step": "experiences",
            "basics": {"name": "Test"},
            "skills": ["Python", "SQL"],
            "nested": {"deep": {"value": 123}}
        }
        db_session.commit()
        db_session.refresh(test_job)
        
        assert test_job.answers["_step"] == "experiences"
        assert test_job.answers["skills"] == ["Python", "SQL"]
        assert test_job.answers["nested"]["deep"]["value"] == 123

    def test_job_requires_user(self, db_session):
        """Test job requires valid user_id"""
        job = Job(
            user_id="invalid_user_id",  # Non-existent user
            type="resume"
        )
        db_session.add(job)
        
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_job_user_relationship(self, db_session, test_job, test_user):
        """Test job belongs to user"""
        assert test_job.user.id == test_user.id
        assert test_job.user.telegram_user_id == test_user.telegram_user_id


class TestMessageModel:
    """Test Message model"""

    def test_create_message(self, db_session, test_job):
        msg = Message(
            user_id=test_job.user_id,
            job_id=test_job.id,
            direction="inbound",
            content="Hello bot",
        )
        db_session.add(msg)
        db_session.commit()

        assert msg.id is not None
        assert msg.direction == "inbound"
        assert msg.content == "Hello bot"
        assert msg.created_at is not None

    def test_message_directions(self, db_session, test_job):
        for direction in ["inbound", "outbound"]:
            msg = Message(
                user_id=test_job.user_id,
                job_id=test_job.id,
                direction=direction,
                content="test",
            )
            db_session.add(msg)
            db_session.commit()
            assert msg.direction == direction
            db_session.delete(msg)
            db_session.commit()

    def test_message_deleted_when_job_deleted(self, db_session, test_job):
        """Job.messages uses delete-orphan cascade — removing the job removes its messages."""
        msg = Message(
            user_id=test_job.user_id,
            job_id=test_job.id,
            direction="inbound",
            content="test",
        )
        db_session.add(msg)
        db_session.commit()
        msg_id = msg.id

        db_session.delete(test_job)
        db_session.commit()

        assert db_session.query(Message).filter(Message.id == msg_id).first() is None


class TestModelRelationships:
    """Test relationships between models"""

    def test_user_to_jobs(self, db_session, test_user):
        """Test user can have multiple jobs"""
        job1 = Job(user_id=test_user.id, type="resume")
        job2 = Job(user_id=test_user.id, type="cv")
        job3 = Job(user_id=test_user.id, type="cover")
        
        db_session.add_all([job1, job2, job3])
        db_session.commit()
        
        db_session.refresh(test_user)
        assert len(test_user.jobs) >= 3  # At least 3 (might have more from fixtures)

    def test_job_to_messages(self, db_session, test_job):
        """Test job can have multiple messages"""
        uid = test_job.user_id
        messages = [
            Message(user_id=uid, job_id=test_job.id, direction="inbound", content="msg1"),
            Message(user_id=uid, job_id=test_job.id, direction="outbound", content="msg2"),
            Message(user_id=uid, job_id=test_job.id, direction="inbound", content="msg3"),
        ]
        db_session.add_all(messages)
        db_session.commit()
        
        db_session.refresh(test_job)
        assert len(test_job.messages) == 3



class TestModelValidation:
    """Test model-level validation and edge cases"""

    def test_user_requires_telegram_id(self, db_session):
        user = User(telegram_username="test")
        db_session.add(user)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_job_default_status(self, db_session, test_user):
        """Test job has default status"""
        job = Job(user_id=test_user.id, type="resume")
        db_session.add(job)
        db_session.commit()
        
        assert job.status == "collecting"  # Default

    def test_job_default_answers(self, db_session, test_user):
        """Test job has default empty answers"""
        job = Job(user_id=test_user.id, type="resume")
        db_session.add(job)
        db_session.commit()
        
        assert job.answers == {}  # Default empty dict

    def test_long_content(self, db_session, test_job):
        """Test message can store long content"""
        long_content = "x" * 10000  # 10KB text
        msg = Message(
            user_id=test_job.user_id,
            job_id=test_job.id,
            direction="inbound",
            content=long_content,
        )
        db_session.add(msg)
        db_session.commit()
        
        assert len(msg.content) == 10000

    def test_special_characters_in_answers(self, db_session, test_job):
        """Test answers can store special characters"""
        test_job.answers = {
            "name": "José María O'Brien-Smith",
            "company": "Tech & Innovation Co., Ltd.",
            "bullet": "Increased revenue by 25% ($1.5M → $2M) in Q1'23"
        }
        db_session.commit()
        db_session.refresh(test_job)
        
        assert "José María" in test_job.answers["name"]
        assert "Tech & Innovation" in test_job.answers["company"]
