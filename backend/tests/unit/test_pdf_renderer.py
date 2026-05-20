"""
Tests for PDF generation using ReportLab
"""
import pytest
from pathlib import Path
from app.services import pdf_renderer


# Sample resume data for testing
SAMPLE_DATA = {
    "basics": {
        "name": "John Doe",
        "title": "Senior Software Engineer",
        "email": "john.doe@example.com",
        "phone": "+1-234-567-8900",
        "location": "San Francisco, CA"
    },
    "target_role": "Senior Backend Engineer",
    "summary": "Experienced software engineer with 8+ years building scalable backend systems. Proficient in Python, Go, and distributed systems architecture. Led teams of 5-10 engineers delivering high-impact products.",
    "skills": [
        "Python",
        "Go",
        "PostgreSQL",
        "Docker",
        "Kubernetes",
        "AWS",
        "Microservices",
        "API Design"
    ],
    "experiences": [
        {
            "company": "TechCorp Inc",
            "title": "Senior Software Engineer",
            "city": "San Francisco",
            "start": "Jan 2020",
            "end": "Present",
            "bullets": [
                "Built distributed API serving 10M+ requests/day with 99.99% uptime",
                "Reduced database query time by 60% through indexing and caching strategies",
                "Mentored 3 junior engineers, improving team velocity by 40%",
                "Designed and implemented microservices architecture for payment processing"
            ]
        },
        {
            "company": "StartupXYZ",
            "title": "Backend Engineer",
            "city": "New York",
            "start": "Jun 2017",
            "end": "Dec 2019",
            "bullets": [
                "Developed REST APIs using Python/Flask serving 100K daily active users",
                "Implemented automated testing pipeline, reducing bugs by 50%",
                "Optimized database queries, improving response time by 3x"
            ]
        }
    ],
    "education": [
        {
            "institution": "University of California, Berkeley",
            "degree": "Bachelor of Science",
            "degree_type": "Computer Science",
            "years": "2013 - 2017"
        }
    ],
    "profiles": [
        {
            "platform": "LinkedIn",
            "url": "https://linkedin.com/in/johndoe"
        },
        {
            "platform": "GitHub",
            "url": "https://github.com/johndoe"
        }
    ],
    "certifications": [
        {
            "name": "AWS Solutions Architect",
            "issuing_body": "Amazon Web Services",
            "year": "2021"
        }
    ],
    "projects": [
        {
            "details": "Open-source contributor to FastAPI framework - added 5 features with 1K+ stars"
        },
        {
            "details": "Built personal finance tracker app with 10K+ downloads on App Store"
        }
    ]
}


class TestPDFGeneration:
    """Tests for PDF generation from data"""
    
    def test_template_1_generates_valid_pdf(self):
        """Test that Template 1 generates a valid PDF"""
        pdf_bytes = pdf_renderer.render_template_1_pdf(SAMPLE_DATA)
        
        assert pdf_bytes is not None
        assert len(pdf_bytes) > 0
        # PDF files start with %PDF-
        assert pdf_bytes[:4] == b'%PDF'
    
    def test_template_2_generates_valid_pdf(self):
        """Test that Template 2 generates a valid PDF"""
        pdf_bytes = pdf_renderer.render_template_2_pdf(SAMPLE_DATA)
        
        assert pdf_bytes is not None
        assert len(pdf_bytes) > 0
        assert pdf_bytes[:4] == b'%PDF'
    
    def test_template_3_generates_valid_pdf(self):
        """Test that Template 3 generates a valid PDF"""
        pdf_bytes = pdf_renderer.render_template_3_pdf(SAMPLE_DATA)
        
        assert pdf_bytes is not None
        assert len(pdf_bytes) > 0
        assert pdf_bytes[:4] == b'%PDF'
    
    def test_render_pdf_from_data_routing(self):
        """Test that render_pdf_from_data correctly routes to template renderers"""
        # Test Template 1
        pdf1 = pdf_renderer.render_pdf_from_data(SAMPLE_DATA, 'template_1')
        assert pdf1 is not None
        assert pdf1[:4] == b'%PDF'
        
        # Test Template 2
        pdf2 = pdf_renderer.render_pdf_from_data(SAMPLE_DATA, 'template_2')
        assert pdf2 is not None
        assert pdf2[:4] == b'%PDF'
        
        # Test Template 3
        pdf3 = pdf_renderer.render_pdf_from_data(SAMPLE_DATA, 'template_3')
        assert pdf3 is not None
        assert pdf3[:4] == b'%PDF'
    
    def test_invalid_template_raises_error(self):
        """Test that invalid template name raises ValueError"""
        with pytest.raises(ValueError, match="Unknown template"):
            pdf_renderer.render_pdf_from_data(SAMPLE_DATA, 'template_invalid')
    
    def test_minimal_data_generates_pdf(self):
        """Test PDF generation with minimal data"""
        minimal_data = {
            "basics": {
                "name": "Jane Smith",
                "email": "jane@example.com"
            },
            "skills": ["Python", "JavaScript"],
            "experiences": []
        }
        
        pdf_bytes = pdf_renderer.render_template_1_pdf(minimal_data)
        assert pdf_bytes is not None
        assert pdf_bytes[:4] == b'%PDF'
    
    def test_currency_symbol_handling(self):
        """Test that Naira currency symbols are handled correctly"""
        data_with_naira = SAMPLE_DATA.copy()
        data_with_naira["experiences"] = [{
            "company": "NaijaTech",
            "title": "Engineer",
            "city": "Lagos",
            "start": "2020",
            "end": "2022",
            "bullets": [
                "Managed budget of ₦50,000,000",
                "Reduced costs by ₦10M annually"
            ]
        }]
        
        pdf_bytes = pdf_renderer.render_template_1_pdf(data_with_naira)
        assert pdf_bytes is not None
        assert pdf_bytes[:4] == b'%PDF'
    
    def test_empty_skills_list(self):
        """Test PDF generation with empty or invalid skills"""
        data_empty_skills = SAMPLE_DATA.copy()
        data_empty_skills["skills"] = []
        
        pdf_bytes = pdf_renderer.render_template_1_pdf(data_empty_skills)
        assert pdf_bytes is not None
        
        # Test with invalid skills (numbers, empty strings)
        data_invalid_skills = SAMPLE_DATA.copy()
        data_invalid_skills["skills"] = ["", "1", "2", "Python", " ", "JavaScript"]
        
        pdf_bytes2 = pdf_renderer.render_template_1_pdf(data_invalid_skills)
        assert pdf_bytes2 is not None
    
    def test_long_content_handling(self):
        """Test PDF generation with very long content"""
        long_data = SAMPLE_DATA.copy()
        long_data["summary"] = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 20
        long_data["experiences"][0]["bullets"] = [
            "Achieved remarkable results in a complex technical environment by implementing cutting-edge solutions and collaborating with cross-functional teams across multiple time zones and departments",
            "Led a major initiative that transformed the entire engineering organization's approach to software development and deployment processes"
        ] * 5
        
        pdf_bytes = pdf_renderer.render_template_1_pdf(long_data)
        assert pdf_bytes is not None
        assert pdf_bytes[:4] == b'%PDF'


class TestPDFOutput:
    """Tests for PDF output file generation (optional - saves test PDFs)"""
    
    @pytest.mark.skipif(True, reason="Manual test - uncomment to generate test PDFs")
    def test_generate_sample_pdfs(self, tmp_path):
        """Generate sample PDFs for manual inspection"""
        # Template 1
        pdf1 = pdf_renderer.render_template_1_pdf(SAMPLE_DATA)
        output1 = tmp_path / "sample_template1.pdf"
        output1.write_bytes(pdf1)
        print(f"\nGenerated: {output1}")
        
        # Template 2
        pdf2 = pdf_renderer.render_template_2_pdf(SAMPLE_DATA)
        output2 = tmp_path / "sample_template2.pdf"
        output2.write_bytes(pdf2)
        print(f"Generated: {output2}")
        
        # Template 3
        pdf3 = pdf_renderer.render_template_3_pdf(SAMPLE_DATA)
        output3 = tmp_path / "sample_template3.pdf"
        output3.write_bytes(pdf3)
        print(f"Generated: {output3}")
        
        assert output1.exists()
        assert output2.exists()
        assert output3.exists()
