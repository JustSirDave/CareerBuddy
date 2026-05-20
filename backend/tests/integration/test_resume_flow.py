"""
Tests for resume conversation flow
"""
import pytest
from app.flows import resume


class TestParsers:
    """Test parsing functions"""

    def test_parse_basics(self):
        """Test basic info parsing"""
        line = "John Doe, john@example.com, +1234567890, New York USA"
        result = resume.parse_basics(line)

        assert result['name'] == "John Doe"
        assert result['email'] == "john@example.com"
        assert result['phone'] == "+1234567890"
        assert result['location'] == "New York USA"

    def test_parse_basics_missing_fields(self):
        """Test parsing with missing fields"""
        line = "John Doe"
        result = resume.parse_basics(line)

        assert result['name'] == "John Doe"
        assert result['email'] == ""  # Padded
        assert result['phone'] == ""
        assert result['location'] == ""

    def test_parse_skills(self):
        """Test skills parsing"""
        text = "Python, FastAPI, PostgreSQL, Docker, Redis"
        result = resume.parse_skills(text)

        assert len(result) == 5
        assert "Python" in result
        assert "FastAPI" in result
        assert "Redis" in result

    def test_parse_skills_with_spaces(self):
        """Test skills with extra spacing"""
        text = "Python,  FastAPI , PostgreSQL,Docker"
        result = resume.parse_skills(text)

        assert len(result) == 4
        assert "Python" in result
        assert "FastAPI" in result
        assert "PostgreSQL" in result

    def test_parse_experience_header(self):
        """Test experience header parsing"""
        line = "Backend Engineer, TechCorp, NYC, Jan 2020, Present"
        result = resume.parse_experience_header(line)

        assert result['role'] == "Backend Engineer"
        assert result['company'] == "TechCorp"
        assert result['location'] == "NYC"
        assert result['start'] == "Jan 2020"
        assert result['end'] == "Present"
        assert result['bullets'] == []

    def test_parse_experience_header_missing_fields(self):
        """Test experience with missing fields"""
        line = "Engineer, Company"
        result = resume.parse_experience_header(line)

        assert result['role'] == "Engineer"
        assert result['company'] == "Company"
        assert result['location'] == ""
        assert result['start'] == ""
        assert result['end'] == ""


class TestValidators:
    """Test validation functions"""

    def test_validate_basics_valid(self):
        """Test valid basics validation"""
        basics = {
            'name': 'John Doe',
            'email': 'john@example.com',
            'title': 'Engineer'
        }
        assert resume.validate_basics(basics) is True

    def test_validate_basics_missing_name(self):
        """Test basics without name"""
        basics = {'email': 'john@example.com'}
        assert resume.validate_basics(basics) is False

    def test_validate_basics_missing_email(self):
        """Test basics without email"""
        basics = {'name': 'John Doe'}
        assert resume.validate_basics(basics) is False

    def test_validate_experience_valid(self):
        """Test valid experience validation"""
        exp = {'role': 'Engineer', 'company': 'TechCorp'}
        assert resume.validate_experience(exp) is True

    def test_validate_experience_missing_role(self):
        """Test experience without role"""
        exp = {'company': 'TechCorp'}
        assert resume.validate_experience(exp) is False


class TestSummaryGeneration:
    """Test summary generation"""

    def test_draft_summary_with_all_fields(self):
        """Test summary with complete data"""
        ctx = {
            'basics': {'title': 'Backend Engineer', 'name': 'John'},
            'skills': ['Python', 'FastAPI', 'PostgreSQL'],
            'experiences': [
                {'company': 'TechCorp', 'role': 'Engineer'}
            ]
        }
        summary = resume.draft_summary(ctx)

        assert 'engineer' in summary.lower()
        assert 'TechCorp' in summary
        assert 'Python' in summary

    def test_draft_summary_no_experience(self):
        """Test summary without experience"""
        ctx = {
            'basics': {'title': 'Engineer'},
            'skills': ['Python'],
            'experiences': []
        }
        summary = resume.draft_summary(ctx)

        assert 'Engineer' in summary or 'engineer' in summary
        assert len(summary) > 20  # Should have some content

    def test_draft_summary_no_skills(self):
        """Test summary without skills"""
        ctx = {
            'basics': {'title': 'Engineer'},
            'skills': [],
            'experiences': [{'company': 'Corp'}]
        }
        summary = resume.draft_summary(ctx)

        assert len(summary) > 20
        assert 'Engineer' in summary or 'engineer' in summary


class TestContextInitialization:
    """Test conversation context setup"""

    def test_start_context_structure(self):
        """Test initial context has correct structure"""
        ctx = resume.start_context()

        assert 'basics' in ctx
        assert 'summary' in ctx
        assert 'skills' in ctx
        assert 'experiences' in ctx
        assert 'education' in ctx
        assert 'projects' in ctx
        assert '_step' in ctx

    def test_start_context_defaults(self):
        """Test default values"""
        ctx = resume.start_context()

        assert ctx['basics'] == {}
        assert ctx['summary'] == ""
        assert ctx['skills'] == []
        assert ctx['experiences'] == []
        assert ctx['_step'] == "basics"
