"""
Tests for conversation router service
Tests critical business logic for resume/CV/cover letter flows
"""
import pytest
from unittest.mock import patch
from app.config import settings
from app.services.conversation_router import (
    FORCE_LOWER,
    GREETINGS,
    RESETS,
    _generate_filename,
    get_active_job,
    handle_cover,
    handle_inbound,
    handle_resume,
    infer_type,
    is_admin,
)
from app.models import User, Job


class TestTypeInference:
    """Test document type inference"""

    def test_infer_resume_button(self):
        assert infer_type("choose_resume") == "resume"

    def test_infer_cv_button(self):
        assert infer_type("choose_cv") == "cv"

    def test_infer_cover_button(self):
        assert infer_type("choose_cover") == "cover"

    def test_infer_from_text(self):
        assert infer_type("I want a resume") == "resume"
        assert infer_type("CV please") == "cv"
        assert infer_type("cover letter") == "cover"

    def test_infer_case_insensitive(self):
        assert infer_type("RESUME") == "resume"
        assert infer_type("Cv") == "cv"
        assert infer_type("COVER LETTER") == "cover"

    def test_infer_none_for_greetings(self):
        assert infer_type("hello") is None
        assert infer_type("hi") is None
        assert infer_type("help") is None

    def test_infer_none_empty(self):
        assert infer_type("") is None


class TestHelpers:
    def test_force_lower(self):
        assert FORCE_LOWER("HELLO") == "hello"
        assert FORCE_LOWER("  Test  ") == "test"
        assert FORCE_LOWER(None) == ""
        assert FORCE_LOWER("") == ""

    def test_force_lower_preserves_words(self):
        assert FORCE_LOWER("Hello World") == "hello world"


class TestFilenameGeneration:
    """Test filename generation"""

    def test_generate_resume_filename(self, db_session, test_user):
        job = Job(
            user_id=test_user.id,
            type="resume",
            answers={
                "basics": {"name": "John Doe"},
                "target_role": "Backend Engineer",
            },
        )
        filename = _generate_filename(job)
        assert filename == "John Doe - Resume.docx"

    def test_generate_cv_filename(self, db_session, test_user):
        job = Job(
            user_id=test_user.id,
            type="cv",
            answers={"basics": {"name": "Jane Smith"}},
        )
        filename = _generate_filename(job)
        assert filename == "Jane Smith - CV.docx"

    def test_generate_cover_filename(self, db_session, test_user):
        job = Job(
            user_id=test_user.id,
            type="cover",
            answers={"basics": {"name": "Alex Brown"}},
        )
        filename = _generate_filename(job)
        assert filename == "Alex Brown - Cover Letter.docx"

    def test_filename_with_special_characters(self, db_session, test_user):
        job = Job(
            user_id=test_user.id,
            type="resume",
            answers={"basics": {"name": "José María O'Brien"}},
        )
        filename = _generate_filename(job)
        assert "José María O'Brien" in filename or "Jose" in filename


class TestAdminAuthentication:
    """Test admin authentication"""

    @patch.object(settings, "admin_telegram_ids", ["123456"])
    def test_is_admin_valid(self):
        assert is_admin("123456") is True

    @patch.object(settings, "admin_telegram_ids", ["123456"])
    def test_is_admin_invalid(self):
        assert is_admin("999999") is False

    @patch.object(settings, "admin_telegram_ids", [])
    def test_is_admin_empty_list(self):
        assert is_admin("123456") is False


class TestGetActiveJob:
    """Test active job retrieval"""

    def test_get_existing_collecting_job(self, db_session, test_user):
        job = Job(
            user_id=test_user.id,
            type="resume",
            status="collecting",
            answers={"_step": "basics"},
        )
        db_session.add(job)
        db_session.commit()

        found_job = get_active_job(db_session, test_user.id, "resume")
        assert found_job is not None
        assert found_job.id == job.id

    def test_creates_new_job_for_different_doc_type(self, db_session, test_user):
        job = Job(
            user_id=test_user.id,
            type="resume",
            status="collecting",
            answers={"_step": "basics"},
        )
        db_session.add(job)
        db_session.commit()

        found_job = get_active_job(db_session, test_user.id, "cv")
        assert found_job is not None
        assert found_job.type == "cv"
        assert found_job.status == "collecting"

    def test_done_resume_triggers_new_collecting_job(self, db_session, test_user):
        job = Job(user_id=test_user.id, type="resume", status="done")
        db_session.add(job)
        db_session.commit()

        found_job = get_active_job(db_session, test_user.id, "resume")
        assert found_job is not None
        assert found_job.status == "collecting"


@pytest.mark.asyncio
class TestHandleInbound:
    """Test main inbound message handler"""

    async def test_welcome_message(self, db_session):
        response = await handle_inbound(db_session, "new_user_123", "hello")

        assert "Welcome" in response or "welcome" in response.lower()

        user = db_session.query(User).filter(User.telegram_user_id == "new_user_123").first()
        assert user is not None

    async def test_reset_command(self, db_session, test_user, test_job):
        response = await handle_inbound(
            db_session,
            test_user.telegram_user_id,
            "/reset",
        )

        assert response == "__SHOW_MENU__"

    async def test_help_command(self, db_session, test_user):
        response = await handle_inbound(
            db_session,
            test_user.telegram_user_id,
            "/help",
        )

        assert response is not None
        assert len(response) > 0

    async def test_status_command(self, db_session, test_user, test_job):
        response = await handle_inbound(
            db_session,
            test_user.telegram_user_id,
            "/status",
        )

        assert response is not None

    @patch("app.services.conversation_router.is_admin", return_value=True)
    @patch("app.services.conversation_router.get_admin_stats")
    async def test_admin_command(self, mock_stats, mock_is_admin, db_session, test_user):
        mock_stats.return_value = "📊 *Career Buddy - Analytics Dashboard*\n"

        response = await handle_inbound(
            db_session,
            test_user.telegram_user_id,
            "/admin",
        )

        assert "Analytics" in response or "Dashboard" in response or "stats" in response.lower()

    @patch("app.services.conversation_router.is_admin", return_value=False)
    async def test_admin_command_unauthorized(self, mock_is_admin, db_session, test_user):
        response = await handle_inbound(
            db_session,
            test_user.telegram_user_id,
            "/admin",
        )

        assert "administrator" in response.lower() or "only" in response.lower()


@pytest.mark.asyncio
class TestHandleResume:
    """Test resume conversation flow"""

    async def test_basics_step_valid_input(self, db_session, test_user):
        job = Job(
            user_id=test_user.id,
            type="resume",
            status="collecting",
            answers={"_step": "basics"},
        )
        db_session.add(job)
        db_session.commit()

        response = await handle_resume(
            db_session,
            job,
            "John Doe, john@example.com, +2348012345678, Lagos Nigeria",
        )

        db_session.refresh(job)
        assert job.answers.get("basics") is not None
        assert job.answers["basics"]["name"] == "John Doe"
        assert "target role" in response.lower() or "role" in response.lower()

    async def test_basics_step_invalid_input(self, db_session, test_user):
        job = Job(
            user_id=test_user.id,
            type="resume",
            status="collecting",
            answers={"_step": "basics"},
        )
        db_session.add(job)
        db_session.commit()

        response = await handle_resume(db_session, job, "Just a name")

        assert "format" in response.lower() or "example" in response.lower() or "comma" in response.lower()

    async def test_target_role_step(self, db_session, test_user):
        job = Job(
            user_id=test_user.id,
            type="resume",
            status="collecting",
            answers={
                "_step": "target_role",
                "basics": {"name": "John Doe"},
            },
        )
        db_session.add(job)
        db_session.commit()

        response = await handle_resume(db_session, job, "Backend Engineer")

        db_session.refresh(job)
        assert job.answers.get("target_role") == "Backend Engineer"

    async def test_education_valid_format(self, db_session, test_user):
        job = Job(
            user_id=test_user.id,
            type="resume",
            status="collecting",
            answers={
                "_step": "education",
                "basics": {"name": "Test"},
                "experiences": [],
            },
        )
        db_session.add(job)
        db_session.commit()

        await handle_resume(
            db_session,
            job,
            "B.Sc. Computer Science, MIT, 2020",
        )

        db_session.refresh(job)
        assert len(job.answers.get("education", [])) > 0

    async def test_skip_education_advances_step(self, db_session, test_user):
        job = Job(
            user_id=test_user.id,
            type="resume",
            status="collecting",
            answers={
                "_step": "education",
                "basics": {"name": "Test"},
                "experiences": [],
            },
        )
        db_session.add(job)
        db_session.commit()

        await handle_resume(db_session, job, "skip")

        db_session.refresh(job)
        assert job.answers["_step"] != "education"

    @patch("app.services.ai.generate_skills")
    async def test_skills_ai_generation(self, mock_ai, db_session, test_user):
        mock_ai.return_value = ["Python", "SQL", "Docker", "AWS", "FastAPI"]

        job = Job(
            user_id=test_user.id,
            type="resume",
            status="collecting",
            answers={
                "_step": "skills",
                "target_role": "Backend Engineer",
                "basics": {"name": "Test"},
            },
        )
        db_session.add(job)
        db_session.commit()

        response = await handle_resume(db_session, job, "")

        assert any(str(i) in response for i in range(1, 6))

    async def test_skills_selection(self, db_session, test_user):
        job = Job(
            user_id=test_user.id,
            type="resume",
            status="collecting",
            answers={
                "_step": "skills",
                "ai_suggested_skills": ["Python", "SQL", "Docker", "AWS", "FastAPI"],
                "basics": {"name": "Test"},
            },
        )
        db_session.add(job)
        db_session.commit()

        await handle_resume(db_session, job, "1,2,3")

        db_session.refresh(job)
        assert len(job.answers.get("skills", [])) == 3

    async def test_invalid_skill_selection(self, db_session, test_user):
        job = Job(
            user_id=test_user.id,
            type="resume",
            status="collecting",
            answers={
                "_step": "skills",
                "ai_suggested_skills": ["Python", "SQL", "Docker"],
                "basics": {"name": "Test"},
            },
        )
        db_session.add(job)
        db_session.commit()

        response = await handle_resume(db_session, job, "python, sql")

        assert "invalid" in response.lower() or "3" in response or "least" in response.lower()


@pytest.mark.asyncio
class TestHandleCover:
    """Test cover letter conversation flow"""

    async def test_basics_step(self, db_session, test_user):
        job = Job(
            user_id=test_user.id,
            type="cover",
            status="collecting",
            answers={"_step": "basics"},
        )
        db_session.add(job)
        db_session.commit()

        await handle_cover(
            db_session,
            job,
            "Alex Johnson, alex@example.com, +2348023456789, Boston MA",
        )

        db_session.refresh(job)
        assert job.answers.get("basics") is not None
        assert job.answers["basics"]["name"] == "Alex Johnson"

    async def test_role_company_step(self, db_session, test_user):
        job = Job(
            user_id=test_user.id,
            type="cover",
            status="collecting",
            answers={
                "_step": "role_company",
                "basics": {"name": "Test"},
            },
        )
        db_session.add(job)
        db_session.commit()

        await handle_cover(
            db_session,
            job,
            "Senior Engineer, Google",
        )

        db_session.refresh(job)
        assert job.answers.get("cover_role") == "Senior Engineer"
        assert job.answers.get("cover_company") == "Google"

    async def test_invalid_role_company_format(self, db_session, test_user):
        job = Job(
            user_id=test_user.id,
            type="cover",
            status="collecting",
            answers={
                "_step": "role_company",
                "basics": {"name": "Test"},
            },
        )
        db_session.add(job)
        db_session.commit()

        response = await handle_cover(
            db_session,
            job,
            "Just a role",
        )

        assert "format" in response.lower() or "example" in response.lower()


class TestConversationEdgeCases:
    """Test edge cases in conversation flows"""

    @pytest.mark.asyncio
    async def test_empty_message(self, db_session, test_user):
        response = await handle_inbound(db_session, test_user.telegram_user_id, "")
        assert response is not None
        assert len(response) > 0

    @pytest.mark.asyncio
    async def test_very_long_message(self, db_session, test_user):
        long_text = "x" * 5000
        response = await handle_inbound(db_session, test_user.telegram_user_id, long_text)
        assert response is not None

    @pytest.mark.asyncio
    async def test_special_characters(self, db_session, test_user):
        special_text = "Test @#$%^&*() 你好 🎉"
        response = await handle_inbound(db_session, test_user.telegram_user_id, special_text)
        assert response is not None

    @pytest.mark.asyncio
    async def test_concurrent_job_types(self, db_session, test_user):
        test_user.onboarding_complete = True
        db_session.commit()

        job1 = Job(
            user_id=test_user.id,
            type="resume",
            status="collecting",
            answers={"_step": "basics"},
        )
        db_session.add(job1)
        db_session.commit()

        await handle_inbound(
            db_session,
            test_user.telegram_user_id,
            "resume",
        )

        jobs = (
            db_session.query(Job)
            .filter(
                Job.user_id == test_user.id,
                Job.type == "resume",
                Job.status == "collecting",
            )
            .all()
        )

        assert len(jobs) == 1


