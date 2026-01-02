"""
AI service for generating skills and summaries using OpenAI.
"""
from typing import List, Dict
from loguru import logger
from openai import OpenAI
from app.config import settings

# Initialize OpenAI client
client = None
if settings.openai_api_key:
    client = OpenAI(api_key=settings.openai_api_key)


def generate_skills(target_role: str, basics: Dict, experiences: List[Dict], tier: str = "free") -> List[str]:
    """
    Generate role-specific skill suggestions using OpenAI.

    Args:
        target_role: The target role/position the user is applying for
        basics: User's basic information (name, title, location, etc.)
        experiences: List of work experiences
        tier: User tier (free or pro)

    Returns:
        List of 8-10 suggested skills
    """
    if not client:
        logger.warning("[ai] OpenAI client not configured, returning fallback skills")
        return get_fallback_skills(target_role)

    # Route to appropriate tier
    if tier == "pro":
        return _generate_skills_pro(target_role, basics, experiences)
    else:
        return _generate_skills_basic(target_role, basics, experiences)


def _generate_skills_basic(target_role: str, basics: Dict, experiences: List[Dict]) -> List[str]:
    """Basic skill generation for free tier - simpler prompt."""
    try:
        # Simple prompt for free tier
        prompt = f"""List 8-10 relevant skills for a {target_role} role.

Include a mix of technical and soft skills appropriate for this position.

Return ONLY a comma-separated list of skills, nothing else.

Example format: Python, Data Analysis, SQL, Communication, Problem Solving"""

        logger.info(f"[ai] Generating basic skills for role: {target_role}")

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a resume expert."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=150
        )

        skills_text = response.choices[0].message.content.strip()
        skills = [s.strip() for s in skills_text.split(",") if s.strip()]

        logger.info(f"[ai] Generated {len(skills)} basic skills")
        return skills[:10]

    except Exception as e:
        logger.error(f"[ai] Error generating basic skills: {e}")
        return get_fallback_skills(target_role)


def _generate_skills_pro(target_role: str, basics: Dict, experiences: List[Dict]) -> List[str]:
    """Enhanced skill generation for pro tier - detailed analysis."""
    try:
        # Build detailed context from user data
        context_parts = [f"Target Role: {target_role}"]

        if basics.get("title"):
            context_parts.append(f"Current Title: {basics['title']}")

        if experiences:
            context_parts.append("\nWork Experience:")
            for exp in experiences[:3]:
                role = exp.get("role", "Unknown Role")
                company = exp.get("company", "Unknown Company")
                context_parts.append(f"- {role} at {company}")
                bullets = exp.get("bullets", [])
                for bullet in bullets[:2]:
                    context_parts.append(f"  • {bullet}")

        context = "\n".join(context_parts)

        prompt = f"""Based on the following information about a job candidate, suggest 8-10 highly relevant, specific skills for their resume.

{context}

PRO TIER Requirements:
- Extract tools/technologies mentioned in their experience (e.g., Python, SQL, Power BI)
- Identify domain expertise from their work (e.g., ETL, Data Warehousing, Statistical Analysis)
- Include advanced technical skills relevant to {target_role}
- Add strategic soft skills (Leadership, Stakeholder Management)
- Ensure skills demonstrate seniority appropriate for their experience level
- Make skills specific and quantifiable where possible

Return ONLY a comma-separated list of skills, nothing else.

Example: Python, SQL, Power BI, ETL Pipelines, Data Modeling, Statistical Analysis, Stakeholder Management, Leadership"""

        logger.info(f"[ai] Generating skills for role: {target_role}")

        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Fast and cost-effective
            messages=[
                {"role": "system", "content": "You are a professional resume writer helping candidates identify relevant skills."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=200
        )

        skills_text = response.choices[0].message.content.strip()
        skills = [s.strip() for s in skills_text.split(",") if s.strip()]

        logger.info(f"[ai] Generated {len(skills)} skills: {skills}")
        return skills[:10]  # Return max 10

    except Exception as e:
        logger.error(f"[ai] Error generating skills: {e}")
        return get_fallback_skills(target_role)


def generate_summary(answers: Dict, tier: str = "free") -> str:
    """
    Generate a professional summary from collected resume data using OpenAI.

    Args:
        answers: Complete resume data including basics, skills, experiences, etc.
        tier: User tier (free or pro)

    Returns:
        A 2-3 sentence professional summary
    """
    if not client:
        logger.warning("[ai] OpenAI client not configured, returning fallback summary")
        return get_fallback_summary(answers)

    # Route to appropriate tier
    if tier == "pro":
        return _generate_summary_pro(answers)
    else:
        return _generate_summary_basic(answers)


def _generate_summary_basic(answers: Dict) -> str:
    """Basic summary generation for free tier."""
    try:
        basics = answers.get("basics", {})
        target_role = answers.get("target_role", "")
        skills = answers.get("skills", [])[:3]  # Just top 3 skills
        experiences = answers.get("experiences", [])

        # Simple context
        exp_count = len(experiences)
        company = experiences[0].get("company", "").strip() if experiences else ""

        prompt = f"""Write a brief 2-sentence professional summary for a {target_role}.

Their experience: {exp_count} position(s){f' at {company}' if company else ''}
Key skills: {', '.join(skills) if skills else 'various skills'}

Requirements:
- 2 sentences only
- Natural and professional tone
- Focus on role and core strengths

Example: "Experienced data analyst with strong analytical skills and expertise in SQL and Python. Proven ability to transform complex data into actionable business insights."
"""

        logger.info("[ai] Generating basic summary")

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a professional resume writer."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.8,
            max_tokens=150
        )

        summary = response.choices[0].message.content.strip()
        if summary.startswith('"') and summary.endswith('"'):
            summary = summary[1:-1]

        logger.info(f"[ai] Generated basic summary")
        return summary

    except Exception as e:
        logger.error(f"[ai] Error generating basic summary: {e}")
        return get_fallback_summary(answers)


def _generate_summary_pro(answers: Dict) -> str:
    """Enhanced summary generation for pro tier - detailed analysis."""
    try:
        basics = answers.get("basics", {})
        target_role = answers.get("target_role", "")
        skills = answers.get("skills", [])
        experiences = answers.get("experiences", [])
        education = answers.get("education", [])

        # Build rich context
        context_parts = []

        # Calculate years of experience
        years_exp = len(experiences)
        if experiences:
            context_parts.append(f"Target Role: {target_role}")
            context_parts.append(f"Experience Level: {years_exp} position(s)")

        if skills:
            context_parts.append(f"\nKey Skills: {', '.join(skills)}")

        if experiences:
            context_parts.append("\nWork Experience with Achievements:")
            for exp in experiences[:2]:
                role = exp.get("role", "")
                company = exp.get("company", "")
                start = exp.get("start", "")
                end = exp.get("end", "")
                context_parts.append(f"- {role} at {company} ({start} - {end})")
                bullets = exp.get("bullets", [])
                for bullet in bullets[:3]:
                    context_parts.append(f"  • {bullet}")

        if education:
            context_parts.append("\nEducation:")
            for edu in education[:1]:
                context_parts.append(f"- {edu.get('details', '')}")

        context = "\n".join(context_parts)

        prompt = f"""Based on the following resume information, write a compelling, senior-level professional summary.

{context}

PRO TIER Requirements:
- Write 3 sentences that demonstrate SENIORITY and IMPACT
- Extract and highlight QUANTIFIABLE achievements (percentages, dollar amounts, scale)
- Mention specific TOOLS/TECHNOLOGIES from their experience
- Show BUSINESS IMPACT and strategic value
- Include LEADERSHIP indicators if present (Led, Managed, Drove, etc.)
- Sound natural and human, NOT obviously AI-generated
- Use active, powerful verbs
- Return ONLY the summary text, no quotes, no labels

Example: "Senior Data Analyst with 5+ years of experience transforming complex datasets into actionable business insights that drove $2M+ in strategic decisions. Built automated ETL pipelines processing 5M+ records daily and created executive dashboards in Power BI, reducing manual work by 70% while improving data quality from 85% to 98%. Expert in Python, SQL, and Power BI with proven ability to lead cross-functional data initiatives and communicate insights to C-level stakeholders."
"""

        logger.info("[ai] Generating professional summary")

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a professional resume writer who creates compelling, natural-sounding summaries."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.8,
            max_tokens=250
        )

        summary = response.choices[0].message.content.strip()

        # Remove quotes if AI added them
        if summary.startswith('"') and summary.endswith('"'):
            summary = summary[1:-1]

        logger.info(f"[ai] Generated summary: {summary[:100]}...")
        return summary

    except Exception as e:
        logger.error(f"[ai] Error generating summary: {e}")
        return get_fallback_summary(answers)


def get_fallback_skills(target_role: str) -> List[str]:
    """Return generic skills when AI is unavailable."""
    role_lower = target_role.lower()

    # Role-specific fallback skills
    if "data" in role_lower or "analyst" in role_lower:
        return ["Data Analysis", "SQL", "Excel", "Python", "Problem Solving", "Communication", "Critical Thinking", "Reporting"]
    elif "engineer" in role_lower or "developer" in role_lower:
        return ["Software Development", "Problem Solving", "Git", "Testing", "Code Review", "Teamwork", "Communication", "Agile"]
    elif "marketing" in role_lower:
        return ["Digital Marketing", "Content Creation", "SEO", "Analytics", "Communication", "Creativity", "Project Management", "Social Media"]
    elif "sales" in role_lower:
        return ["Sales Strategy", "Client Relations", "Negotiation", "CRM", "Communication", "Presentation", "Teamwork", "Goal-Oriented"]
    else:
        return ["Communication", "Problem Solving", "Teamwork", "Leadership", "Time Management", "Adaptability", "Critical Thinking", "Organization"]


def revamp_resume(original_content: str, tier: str = "free") -> str:
    """
    Revamp/improve an existing resume using AI.

    Args:
        original_content: The user's original resume content
        tier: User tier (free or pro)

    Returns:
        Improved resume content
    """
    if not client:
        logger.warning("[ai] OpenAI client not configured, returning original")
        return original_content

    try:
        if tier == "pro":
            prompt = f"""You are a professional resume writer. Improve the following resume content:

{original_content}

PRO TIER Requirements:
- Enhance all bullet points with quantifiable metrics and business impact
- Use strong action verbs (Led, Drove, Increased, Reduced, etc.)
- Add specific numbers, percentages, and scale where possible
- Highlight leadership and strategic contributions
- Make it ATS-friendly (no special characters, clear formatting)
- Maintain professional tone throughout
- Keep the same structure but improve clarity and impact
- Return the improved content in a clear, organized format

Return the improved resume content."""
        else:
            prompt = f"""You are a resume editor. Improve the following resume content:

{original_content}

FREE TIER Requirements:
- Fix grammar and spelling errors
- Use consistent formatting
- Add action verbs where appropriate
- Improve clarity and readability
- Make it ATS-friendly
- Keep it concise and professional

Return the improved resume content."""

        logger.info(f"[ai] Revamping resume (tier: {tier})")

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a professional resume writer who improves resume content."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1500
        )

        improved = response.choices[0].message.content.strip()
        logger.info(f"[ai] Resume revamped successfully")
        return improved

    except Exception as e:
        logger.error(f"[ai] Error revamping resume: {e}")
        return original_content


def get_fallback_summary(answers: Dict) -> str:
    """Generate a basic summary when AI is unavailable."""
    basics = answers.get("basics", {})
    skills = answers.get("skills", [])
    experiences = answers.get("experiences", [])

    title = (basics.get("title") or "professional").strip()
    company = ""
    if experiences:
        company = experiences[0].get("company", "").strip()

    parts = []

    if company:
        parts.append(f"{title.capitalize()} with hands-on experience at {company}.")
    else:
        parts.append(f"{title.capitalize()} with hands-on experience.")

    if skills:
        parts.append(f"Skilled in {', '.join(skills[:3])}.")
    else:
        parts.append("Delivering reliable results and clean execution.")

    return " ".join(parts)
