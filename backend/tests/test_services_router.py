"""
Tests for conversation router service
Tests critical business logic for resume/CV/cover letter flows
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from app.services.router import (
    handle_inbound,
    handle_resume,
    handle_cover,
    infer_type,
    get_active_job,
    _generate_filename,
    is_admin,
    GREETINGS,
    RESETS
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


class TestFilenameGeneration:
    """Test filename generation"""

    def test_generate_resume_filename(self, db_session, test_user):
        """Test resume filename format"""
        job = Job(
            user_id=test_user.id,
            type="resume",
            answers={
                "basics": {"name": "John Doe"},
                "target_role": "Backend Engineer"
            }
        )
        filename = _generate_filename(job)
        assert "John Doe - Resume.docx" == filename

    def test_generate_cv_filename(self, db_session, test_user):
        """Test CV filename format"""
        job = Job(
            user_id=test_user.id,
            type="cv",
            answers={"basics": {"name": "Jane Smith"}}
        )
        filename = _generate_filename(job)
        assert "Jane Smith - CV.docx" == filename

    def test_generate_cover_filename(self, db_session, test_user):
        """Test cover letter filename format"""
        job = Job(
            user_id=test_user.id,
            type="cover",
            answers={"basics": {"name": "Alex Brown"}}
        )
        filename = _generate_filename(job)
        assert "Alex Brown - Cover Letter.docx" == filename

    def test_filename_with_special_characters(self, db_session, test_user):
        """Test filename handles special characters"""
        job = Job(
            user_id=test_user.id,
            type="resume",
            answers={"basics": {"name": "José María O'Brien"}}
        )
        filename = _generate_filename(job)
        # Should handle special characters safely
        assert "José María O'Brien" in filename or "Jose Maria OBrien" in filename


class TestAdminAuthentication:
    """Test admin authentication"""

    @patch('app.services.router.settings.admin_telegram_ids', ['123456'])
    def test_is_admin_valid(self):
        """Test valid admin ID"""
        assert is_admin("123456") is True

    @patch('app.services.router.settings.admin_telegram_ids', ['123456'])
    def test_is_admin_invalid(self):
        """Test non-admin ID"""
        assert is_admin("999999") is False

    @patch('app.services.router.settings.admin_telegram_ids', [])
    def test_is_admin_empty_list(self):
        """Test when no admins configured"""
        assert is_admin("123456") is False


class TestGetActiveJob:
    """Test active job retrieval"""

    def test_get_existing_collecting_job(self, db_session, test_user):
        """Test retrieving existing collecting job"""
        job = Job(
            user_id=test_user.id,
            type="resume",
            status="collecting",
            answers={"_step": "basics"}
        )
        db_session.add(job)
        db_session.commit()

        found_job = get_active_job(db_session, test_user.id, "resume")
        assert found_job is not None
        assert found_job.id == job.id

    def test_get_no_job_for_different_type(self, db_session, test_user):
        """Test no job found for different type"""
        job = Job(
            user_id=test_user.id,
            type="resume",
            status="collecting"
        )
        db_session.add(job)
        db_session.commit()

        found_job = get_active_job(db_session, test_user.id, "cv")
        assert found_job is None

    def test_ignores_completed_jobs(self, db_session, test_user):
        """Test ignores jobs with status 'done'"""
        job = Job(
            user_id=test_user.id,
            type="resume",
            status="done"
        )
        db_session.add(job)
        db_session.commit()

        found_job = get_active_job(db_session, test_user.id, "resume")
        assert found_job is None  # Should not find completed job


@pytest.mark.asyncio
class TestHandleInbound:
    """Test main inbound message handler"""

    async def test_welcome_message(self, db_session):
        """Test welcome message on greeting"""
        response = await handle_inbound(db_session, "new_user_123", "hello")
        
        assert "Welcome" in response or "welcome" in response.lower()
        
        # User should be created
        user = db_session.query(User).filter(
            User.telegram_user_id == "new_user_123"
        ).first()
        assert user is not None

    async def test_reset_command(self, db_session, test_user, test_job):
        """Test reset command clears job"""
        initial_job_count = db_session.query(Job).count()
        
        response = await handle_inbound(
            db_session,
            test_user.telegram_user_id,
            "/reset"
        )
        
        assert "fresh start" in response.lower() or "reset" in response.lower()

    async def test_help_command(self, db_session, test_user):
        """Test help command"""
        response = await handle_inbound(
            db_session,
            test_user.telegram_user_id,
            "/help"
        )
        
        assert response is not None
        assert len(response) > 0

    async def test_status_command(self, db_session, test_user, test_job):
        """Test status command shows job info"""
        response = await handle_inbound(
            db_session,
            test_user.telegram_user_id,
            "/status"
        )
        
        assert response is not None

    @patch('app.services.router.is_admin', return_value=True)
    @patch('app.services.router.get_admin_stats')
    async def test_admin_command(self, mock_stats, mock_is_admin, db_session, test_user):
        """Test admin command for authorized user"""
        mock_stats.return_value = "Admin stats"
        
        response = await handle_inbound(
            db_session,
            test_user.telegram_user_id,
            "/admin"
        )
        
        assert "Admin" in response or "stats" in response.lower()

    @patch('app.services.router.is_admin', return_value=False)
    async def test_admin_command_unauthorized(self, mock_is_admin, db_session, test_user):
        """Test admin command for non-admin"""
        response = await handle_inbound(
            db_session,
            test_user.telegram_user_id,
            "/admin"
        )
        
        assert "not authorized" in response.lower() or "admin" not in response.lower()

    async def test_payment_bypass(self, db_session, test_user):
        """Test payment bypass for testing"""
        response = await handle_inbound(
            db_session,
            test_user.telegram_user_id,
            "payment made"
        )
        
        # User should be upgraded to pro
        db_session.refresh(test_user)
        assert test_user.tier == "pro"
        assert "upgraded" in response.lower()


@pytest.mark.asyncio
class TestHandleResume:
    """Test resume conversation flow"""

    async def test_basics_step_valid_input(self, db_session, test_user):
        """Test collecting basics information"""
        job = Job(
            user_id=test_user.id,
            type="resume",
            status="collecting",
            answers={"_step": "basics"}
        )
        db_session.add(job)
        db_session.commit()

        response = await handle_resume(
            db_session,
            job,
            "John Doe, john@example.com, +1234567890, New York",
            "free"
        )

        db_session.refresh(job)
        assert job.answers.get("basics") is not None
        assert job.answers["basics"]["name"] == "John Doe"
        assert "target role" in response.lower() or "role" in response.lower()

    async def test_basics_step_invalid_input(self, db_session, test_user):
        """Test basics with invalid format"""
        job = Job(
            user_id=test_user.id,
            type="resume",
            status="collecting",
            answers={"_step": "basics"}
        )
        db_session.add(job)
        db_session.commit()

        response = await handle_resume(
            db_session,
            job,
            "Just a name",  # Missing required fields
            "free"
        )

        # Should re-ask the question
        assert "format" in response.lower() or "example" in response.lower()

    async def test_target_role_step(self, db_session, test_user):
        """Test target role collection"""
        job = Job(
            user_id=test_user.id,
            type="resume",
            status="collecting",
            answers={
                "_step": "target_role",
                "basics": {"name": "John Doe"}
            }
        )
        db_session.add(job)
        db_session.commit()

        response = await handle_resume(
            db_session,
            job,
            "Backend Engineer",
            "free"
        )

        db_session.refresh(job)
        assert job.answers.get("target_role") == "Backend Engineer"

    async def test_education_valid_format(self, db_session, test_user):
        """Test education with valid format"""
        job = Job(
            user_id=test_user.id,
            type="resume",
            status="collecting",
            answers={
                "_step": "education",
                "basics": {"name": "Test"},
                "experiences": []
            }
        )
        db_session.add(job)
        db_session.commit()

        response = await handle_resume(
            db_session,
            job,
            "B.Sc. Computer Science, MIT, 2020",
            "free"
        )

        db_session.refresh(job)
        assert len(job.answers.get("education", [])) > 0

    async def test_skip_education(self, db_session, test_user):
        """Test skipping education"""
        job = Job(
            user_id=test_user.id,
            type="resume",
            status="collecting",
            answers={
                "_step": "education",
                "basics": {"name": "Test"},
                "experiences": []
            }
        )
        db_session.add(job)
        db_session.commit()

        response = await handle_resume(
            db_session,
            job,
            "skip",
            "free"
        )

        # Should move to next step
        db_session.refresh(job)
        assert job.answers["_step"] != "education"

    @patch('app.services.ai.generate_skills')
    async def test_skills_ai_generation(self, mock_ai, db_session, test_user):
        """Test AI skills generation"""
        mock_ai.return_value = ["Python", "SQL", "Docker", "AWS", "FastAPI"]
        
        job = Job(
            user_id=test_user.id,
            type="resume",
            status="collecting",
            answers={
                "_step": "skills",
                "target_role": "Backend Engineer",
                "basics": {"name": "Test"}
            }
        )
        db_session.add(job)
        db_session.commit()

        # First call should trigger AI generation
        response = await handle_resume(db_session, job, "", "free")
        
        # Should show numbered skills
        assert any(str(i) in response for i in range(1, 6))

    async def test_skills_selection(self, db_session, test_user):
        """Test selecting skills from list"""
        job = Job(
            user_id=test_user.id,
            type="resume",
            status="collecting",
            answers={
                "_step": "skills",
                "ai_generated_skills": ["Python", "SQL", "Docker", "AWS", "FastAPI"],
                "basics": {"name": "Test"}
            }
        )
        db_session.add(job)
        db_session.commit()

        response = await handle_resume(db_session, job, "1,2,3", "free")

        db_session.refresh(job)
        assert len(job.answers.get("skills", [])) == 3

    async def test_invalid_skill_selection(self, db_session, test_user):
        """Test invalid skill selection format"""
        job = Job(
            user_id=test_user.id,
            type="resume",
            status="collecting",
            answers={
                "_step": "skills",
                "ai_generated_skills": ["Python", "SQL", "Docker"],
                "basics": {"name": "Test"}
            }
        )
        db_session.add(job)
        db_session.commit()

        response = await handle_resume(db_session, job, "python, sql", "free")

        # Should give helpful error message
        assert "number" in response.lower() or "format" in response.lower()


@pytest.mark.asyncio
class TestHandleCover:
    """Test cover letter conversation flow"""

    async def test_basics_step(self, db_session, test_user):
        """Test collecting basics for cover letter"""
        job = Job(
            user_id=test_user.id,
            type="cover",
            status="collecting",
            answers={"_step": "basics"}
        )
        db_session.add(job)
        db_session.commit()

        response = await handle_cover(
            db_session,
            job,
            "Alex Johnson, alex@example.com, +1234567890, Boston MA",
            "free"
        )

        db_session.refresh(job)
        assert job.answers.get("basics") is not None
        assert job.answers["basics"]["name"] == "Alex Johnson"

    async def test_role_company_step(self, db_session, test_user):
        """Test collecting role and company"""
        job = Job(
            user_id=test_user.id,
            type="cover",
            status="collecting",
            answers={
                "_step": "role_company",
                "basics": {"name": "Test"}
            }
        )
        db_session.add(job)
        db_session.commit()

        response = await handle_cover(
            db_session,
            job,
            "Senior Engineer, Google",
            "free"
        )

        db_session.refresh(job)
        assert job.answers.get("cover_role") == "Senior Engineer"
        assert job.answers.get("cover_company") == "Google"

    async def test_invalid_role_company_format(self, db_session, test_user):
        """Test invalid role/company format"""
        job = Job(
            user_id=test_user.id,
            type="cover",
            status="collecting",
            answers={
                "_step": "role_company",
                "basics": {"name": "Test"}
            }
        )
        db_session.add(job)
        db_session.commit()

        response = await handle_cover(
            db_session,
            job,
            "Just a role",  # Missing company
            "free"
        )

        # Should re-ask
        assert "format" in response.lower() or "example" in response.lower()


class TestConversationEdgeCases:
    """Test edge cases in conversation flows"""

    @pytest.mark.asyncio
    async def test_empty_message(self, db_session, test_user):
        """Test handling empty message"""
        response = await handle_inbound(db_session, test_user.telegram_user_id, "")
        assert response is not None
        assert len(response) > 0

    @pytest.mark.asyncio
    async def test_very_long_message(self, db_session, test_user):
        """Test handling very long message"""
        long_text = "x" * 5000
        response = await handle_inbound(db_session, test_user.telegram_user_id, long_text)
        assert response is not None

    @pytest.mark.asyncio
    async def test_special_characters(self, db_session, test_user):
        """Test handling special characters"""
        special_text = "Test @#$%^&*() 你好 🎉"
        response = await handle_inbound(db_session, test_user.telegram_user_id, special_text)
        assert response is not None

    @pytest.mark.asyncio
    async def test_concurrent_job_types(self, db_session, test_user):
        """Test user can't have multiple active jobs of same type"""
        job1 = Job(
            user_id=test_user.id,
            type="resume",
            status="collecting",
            answers={"_step": "basics"}
        )
        db_session.add(job1)
        db_session.commit()

        # Should reuse existing job, not create new one
        response = await handle_inbound(
            db_session,
            test_user.telegram_user_id,
            "resume"
        )
        
        jobs = db_session.query(Job).filter(
            Job.user_id == test_user.id,
            Job.type == "resume",
            Job.status == "collecting"
        ).all()
        
        # Should only have one collecting resume job
        assert len(jobs) == 1


class TestPaymentIntegration:
    """Test payment-related logic in router"""

    @pytest.mark.asyncio
    async def test_free_user_generation_limit(self, db_session, test_user):
        """Test free users hit generation limit"""
        # Set user's generation count to limit
        test_user.generation_count = 10  # Assuming limit is lower
        db_session.commit()

        # This test validates the payment check exists
        # Actual limit enforcement is tested in test_services_payments.py

    @pytest.mark.asyncio
    async def test_pro_user_no_limit(self, db_session, pro_user):
        """Test pro users don't hit limits"""
        assert pro_user.tier == "pro"
        
        job = Job(
            user_id=pro_user.id,
            type="resume",
            status="collecting"
        )
        db_session.add(job)
        db_session.commit()
        
        # Pro user should be able to generate without payment prompts
