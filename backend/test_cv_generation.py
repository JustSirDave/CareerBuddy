"""
Test script for CV generation using the new render_cv function.
This demonstrates the exact data structure needed to generate a CV
that matches the reference layout.
"""

from app.models.job import Job
from app.services.renderer import render_cv


def create_sample_cv_data():
    """
    Create sample CV data that matches the reference layout structure.
    This shows all the fields supported by the CV renderer.
    """
    return {
        # HEADER SECTION
        "basics": {
            "name": "Adewumi Joyful Oreoluwa",
            "title": "Home Parenting",
            "location": "No 10, First transformer, Olufosm Akure, Ondo state",
            "phone": "+2349070144920",
            "email": "adewumiorooluwa2018@gmail.com"
        },
        
        # PROFILES SECTION
        "profiles": [
            {
                "platform": "LinkedIn",
                "url": "Oreoluwa Joyful Adewumi"
            },
            {
                "platform": "Facebook",
                "url": "Oreoluwa Adewunmi"
            }
        ],
        
        # SUMMARY SECTION
        "summary": (
            "Calm, disciplined, and detail-oriented graduate in Home Economics with strong "
            "interpersonal awareness and a natural sense of order. Known for her soft-spoken nature, "
            "gentle approach, and ability to guide others through both practical and theoretical learning. Brings "
            "a thoughtful, people-centered approach with quiet leadership potential, well-suited for "
            "teaching, mentoring, and supporting family and community development."
        ),
        
        # EXPERIENCE SECTION
        "experiences": [
            {
                "company": "University of Benin catering services. (Blue Meadows)",
                "start": "Jun 2021",
                "end": "May 2022",
                "role": "Store keeper",
                "location": "Benin City",
                "bullets": [
                    "To oversee the distribution of cooking and non-cooking items within and outside the restaurant and to record the expenditure for all purchases in the restaurant."
                ]
            },
            {
                "company": "Living Proof International School",
                "start": "May 2022",
                "end": "Jun 2024",
                "role": "Classroom Teacher",
                "location": "Benin City",
                "bullets": [
                    "Responsible for maintaining daily classroom coordination and instilling educational and moral values in students."
                ]
            },
            {
                "company": "Iseyin District Grammar School Iseyin.",
                "start": "Oct 2024",
                "end": "Aug 2025",
                "role": "Home Economics Teacher",
                "location": "Oyostate, Ibadan",
                "bullets": [
                    "Delivered engaging Food & Nutrition lessons and provided comprehensive instruction in Home Economics education."
                ]
            }
        ],
        
        # EDUCATION SECTION
        "education": [
            {
                "institution": "University of Benin",
                "degree": "BEd. Home Economics",
                "years": "2018-2024",
                "degree_type": "Bachelor of Education"
            }
        ],
        
        # REFERENCES SECTION
        "references": [
            {
                "name": "Mrs Ivie Edosomwan",
                "title": "Secretary \\ Manager of Uniben catering services.",
                "organization": ""
            },
            {
                "name": "Prince Femi Olalete",
                "title": "Vice Principal, IDGS",
                "organization": ""
            }
        ],
        
        # SKILLS SECTION
        "skills": [
            "Empathy",
            "Emotional Intelligence",
            "Communication Skills",
            "Adaptability",
            "Mentorship & Guidance",
            "Problem-solving"
        ]
    }


def test_cv_generation():
    """
    Test the CV generation with sample data.
    This creates a Job object with answers and generates a CV.
    """
    # Create a mock job object
    class MockJob:
        def __init__(self, answers):
            self.id = "test-cv-123"
            self.answers = answers
    
    # Get sample data
    cv_data = create_sample_cv_data()
    
    # Create job with CV data
    job = MockJob(answers=cv_data)
    
    # Generate CV
    cv_bytes = render_cv(job)
    
    # Save to file
    import os
    output_dir = "output"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    output_path = os.path.join(output_dir, "test_cv_sample.docx")
    with open(output_path, "wb") as f:
        f.write(cv_bytes)
    
    print(f"✅ CV generated successfully!")
    print(f"📄 Output saved to: {output_path}")
    print(f"📏 File size: {len(cv_bytes)} bytes")
    
    return output_path


if __name__ == "__main__":
    test_cv_generation()

