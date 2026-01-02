"""
Tests for conversation router
"""
import pytest
from app.services.router import infer_type, FORCE_LOWER


class TestTypeInference:
    """Test document type inference from user input"""

    def test_infer_resume_button(self):
        """Test resume button click"""
        assert infer_type("choose_resume") == "resume"

    def test_infer_cv_button(self):
        """Test CV button click"""
        assert infer_type("choose_cv") == "cv"

    def test_infer_cover_button(self):
        """Test cover letter button click"""
        assert infer_type("choose_cover") == "cover"

    def test_infer_resume_text(self):
        """Test 'resume' in text"""
        assert infer_type("I want a resume") == "resume"
        assert infer_type("Resume please") == "resume"
        assert infer_type("RESUME") == "resume"

    def test_infer_cv_text(self):
        """Test 'cv' detection"""
        assert infer_type("cv") == "cv"
        assert infer_type("I need a CV") == "cv"
        assert infer_type("CV please") == "cv"

    def test_infer_cover_text(self):
        """Test cover letter detection"""
        assert infer_type("cover letter") == "cover"
        assert infer_type("I want a cover") == "cover"

    def test_infer_none(self):
        """Test when no type detected"""
        assert infer_type("hello") is None
        assert infer_type("help") is None
        assert infer_type("") is None


class TestHelpers:
    """Test helper functions"""

    def test_force_lower(self):
        """Test FORCE_LOWER helper"""
        assert FORCE_LOWER("HELLO") == "hello"
        assert FORCE_LOWER("  Test  ") == "test"
        assert FORCE_LOWER(None) == ""
        assert FORCE_LOWER("") == ""

    def test_force_lower_preserves_content(self):
        """Test FORCE_LOWER doesn't corrupt data"""
        assert FORCE_LOWER("Hello World") == "hello world"
        assert FORCE_LOWER("Test123") == "test123"
