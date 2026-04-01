"""
CareerBuddy - AI Service
AI service for generating skills and summaries using OpenAI.
Author: Sir Dave
"""
import json
import re
import time
from typing import List, Dict, Any
from loguru import logger
from openai import OpenAI
from app.config import settings

MAX_AI_RETRIES = 2
AI_RETRY_DELAY = 1.5  # seconds

client = None
if settings.openai_api_key:
    client = OpenAI(api_key=settings.openai_api_key)


def _call_with_retry(fn, *args, fallback=None, **kwargs):
    """Call fn with automatic retry on transient failures. Returns fallback on exhaustion."""
    last_exc = None
    for attempt in range(MAX_AI_RETRIES):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_exc = e
            if attempt < MAX_AI_RETRIES - 1:
                delay = AI_RETRY_DELAY * (attempt + 1)
                logger.warning(f"[ai] Retry {attempt + 1}/{MAX_AI_RETRIES} after {delay}s: {e}")
                time.sleep(delay)
    logger.error(f"[ai] All {MAX_AI_RETRIES} attempts failed: {last_exc}")
    return fallback


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
    prompt = f"""List 8-10 relevant skills for a {target_role} role.

Include a mix of technical and soft skills appropriate for this position.

Return ONLY a comma-separated list of skills, nothing else.

Example format: Python, Data Analysis, SQL, Communication, Problem Solving"""

    logger.info(f"[ai] Generating basic skills for role: {target_role}")

    def _call():
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a resume expert."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=150,
        )
        skills_text = response.choices[0].message.content.strip()
        return [s.strip() for s in skills_text.split(",") if s.strip()][:10]

    result = _call_with_retry(_call, fallback=None)
    if result:
        logger.info(f"[ai] Generated {len(result)} basic skills")
        return result
    return get_fallback_skills(target_role)


def _generate_skills_pro(target_role: str, basics: Dict, experiences: List[Dict]) -> List[str]:
    """Enhanced skill generation for pro tier - detailed analysis."""
    context_parts = [f"Target Role: {target_role}"]
    if basics.get("title"):
        context_parts.append(f"Current Title: {basics['title']}")
    if experiences:
        context_parts.append("\nWork Experience:")
        for exp in experiences[:3]:
            role = exp.get("role", "Unknown Role")
            company = exp.get("company", "Unknown Company")
            context_parts.append(f"- {role} at {company}")
            for bullet in exp.get("bullets", [])[:2]:
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

    logger.info(f"[ai] Generating pro skills for role: {target_role}")

    def _call():
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a professional resume writer helping candidates identify relevant skills."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=200,
        )
        skills_text = response.choices[0].message.content.strip()
        return [s.strip() for s in skills_text.split(",") if s.strip()][:10]

    result = _call_with_retry(_call, fallback=None)
    if result:
        logger.info(f"[ai] Generated {len(result)} pro skills")
        return result
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
    basics = answers.get("basics", {})
    target_role = answers.get("target_role", "")
    skills = answers.get("skills", [])[:3]
    experiences = answers.get("experiences", [])
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

    def _call():
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a professional resume writer."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.8,
            max_tokens=150,
        )
        text = response.choices[0].message.content.strip()
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1]
        return text

    result = _call_with_retry(_call, fallback=None)
    if result:
        logger.info("[ai] Generated basic summary")
        return result
    return get_fallback_summary(answers)


def _generate_summary_pro(answers: Dict) -> str:
    """Enhanced summary generation for pro tier - detailed analysis."""
    target_role = answers.get("target_role", "")
    skills = answers.get("skills", [])
    experiences = answers.get("experiences", [])
    education = answers.get("education", [])

    context_parts = []
    years_exp = len(experiences)
    if experiences:
        context_parts.append(f"Target Role: {target_role}")
        context_parts.append(f"Experience Level: {years_exp} position(s)")
    if skills:
        context_parts.append(f"\nKey Skills: {', '.join(skills)}")
    if experiences:
        context_parts.append("\nWork Experience with Achievements:")
        for exp in experiences[:2]:
            context_parts.append(
                f"- {exp.get('role', '')} at {exp.get('company', '')} "
                f"({exp.get('start', '')} - {exp.get('end', '')})"
            )
            for bullet in exp.get("bullets", [])[:3]:
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

    logger.info("[ai] Generating pro summary")

    def _call():
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a professional resume writer who creates compelling, natural-sounding summaries."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.8,
            max_tokens=250,
        )
        text = response.choices[0].message.content.strip()
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1]
        return text

    result = _call_with_retry(_call, fallback=None)
    if result:
        logger.info(f"[ai] Generated pro summary: {result[:100]}...")
        return result
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

    def _call():
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a professional resume writer who improves resume content."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1500,
        )
        return response.choices[0].message.content.strip()

    result = _call_with_retry(_call, fallback=None)
    if result:
        logger.info("[ai] Resume revamped successfully")
        return result
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


def detect_onboarding_intent(user_message: str) -> Dict[str, Any]:
    """
    Classify user's onboarding message into document intent.
    Returns: {intent, confidence, extracted_role, extracted_company}
    """
    if not client:
        logger.warning("[ai] OpenAI not configured, returning unclear intent")
        return {"intent": "unclear", "confidence": "low", "extracted_role": None, "extracted_company": None}

    prompt = f"""You are an assistant helping classify a job seeker's intent.
Based on their message, return ONLY a JSON object with these exact keys:
- "intent": one of "resume", "cv", "cover_letter", "bundle", "unclear"
- "confidence": "high" or "low"
- "extracted_role": job title if mentioned, else null
- "extracted_company": company name if mentioned, else null

Message: "{user_message}"
"""
    fallback = {"intent": "unclear", "confidence": "low", "extracted_role": None, "extracted_company": None}

    def _call():
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a resume expert. Return only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=150,
        )
        content = response.choices[0].message.content.strip()
        json_match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
        data = json.loads(json_match.group()) if json_match else json.loads(content)
        intent = data.get("intent", "unclear")
        if intent not in ("resume", "cv", "cover_letter", "bundle", "unclear"):
            intent = "unclear"
        return {
            "intent": intent,
            "confidence": data.get("confidence", "low") or "low",
            "extracted_role": data.get("extracted_role"),
            "extracted_company": data.get("extracted_company"),
        }

    result = _call_with_retry(_call, fallback=fallback)
    return result
