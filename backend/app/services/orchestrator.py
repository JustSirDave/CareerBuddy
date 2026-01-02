"""
AI Orchestrator Service - LLM-powered content enhancement
Uses Claude API to improve resume content quality
"""
import json
from typing import Dict, List, Optional
from loguru import logger

from app.config import settings

# Initialize Claude client only if API key is provided
_claude_client = None
if settings.anthropic_api_key:
    try:
        from anthropic import Anthropic
        _claude_client = Anthropic(api_key=settings.anthropic_api_key)
        logger.info("[orchestrator] Claude API initialized successfully")
    except Exception as e:
        logger.warning(f"[orchestrator] Failed to initialize Claude API: {e}")


def enhance_summary(basics: Dict, skills: List[str], experiences: List[Dict]) -> str:
    """
    Use LLM to create a compelling professional summary.

    Args:
        basics: User's basic info (name, title, etc.)
        skills: List of skills
        experiences: List of work experiences

    Returns:
        Enhanced professional summary (2-3 sentences)
    """
    # Fallback to basic summary if no API key
    if not _claude_client:
        logger.warning("[orchestrator] No Claude API key, using fallback summary")
        return _fallback_summary(basics, skills, experiences)

    try:
        title = basics.get('title', 'professional')

        # Build context
        context_parts = [f"Title: {title}"]

        if skills:
            context_parts.append(f"Skills: {', '.join(skills[:8])}")

        if experiences:
            latest_exp = experiences[-1]
            context_parts.append(
                f"Latest role: {latest_exp.get('role', '')} at {latest_exp.get('company', '')}"
            )

            # Calculate years of experience
            if len(experiences) >= 2:
                context_parts.append(f"Number of positions: {len(experiences)}")

        context = "\n".join(context_parts)

        prompt = f"""Create a compelling professional summary for a resume based on this information:

{context}

Requirements:
- 2-3 sentences maximum
- Highlight expertise and value proposition
- Include specific skills and technologies
- Mention measurable impact if discernible
- Use third person (no "I", "my", etc.)
- Professional and confident tone
- ATS-friendly (no special characters)

Return ONLY the summary text, no preamble or explanation."""

        response = _claude_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=200,
            temperature=0.7,
            messages=[{"role": "user", "content": prompt}]
        )

        summary = response.content[0].text.strip()
        logger.info(f"[orchestrator] Generated AI summary: {summary[:100]}...")
        return summary

    except Exception as e:
        logger.error(f"[orchestrator] Failed to generate AI summary: {e}")
        return _fallback_summary(basics, skills, experiences)


def enhance_bullet(bullet: str, role: str, company: str) -> str:
    """
    Improve a single bullet point using AI.
    Adds specificity: numbers, timeframes, impact.

    Args:
        bullet: Original bullet text
        role: Job role
        company: Company name

    Returns:
        Enhanced bullet point
    """
    if not _claude_client:
        return bullet  # Return as-is if no API

    try:
        prompt = f"""Improve this resume bullet point to be more specific and impactful:

Original: {bullet}
Role: {role}
Company: {company}

Requirements:
- Add quantifiable metrics if possible (%, numbers, scale)
- Include timeframe or scope
- Highlight business impact
- Start with strong action verb
- Keep under 150 characters
- ATS-friendly formatting
- No first-person pronouns

If the original already has good specificity, make minor improvements only.
Return ONLY the improved bullet, no explanation."""

        response = _claude_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=150,
            temperature=0.7,
            messages=[{"role": "user", "content": prompt}]
        )

        enhanced = response.content[0].text.strip()

        # Remove leading bullet/dash if LLM added it
        enhanced = enhanced.lstrip('"- ').strip()

        logger.info(f"[orchestrator] Enhanced bullet: {bullet[:50]}... -> {enhanced[:50]}...")
        return enhanced

    except Exception as e:
        logger.error(f"[orchestrator] Failed to enhance bullet: {e}")
        return bullet


def validate_content_quality(job_data: Dict) -> Dict[str, List[str]]:
    """
    Validate content against quality rules.
    Returns suggestions for improvement.

    Args:
        job_data: Full job answers dict

    Returns:
        Dict of {section: [suggestions]}
    """
    suggestions = {}

    # Check summary
    summary = job_data.get('summary', '')
    if summary:
        summary_issues = []
        if len(summary) < 50:
            summary_issues.append("Summary is too short (min 50 chars)")
        if len(summary) > 300:
            summary_issues.append("Summary is too long (max 300 chars)")

        # Check for first-person pronouns
        first_person = ['I ', 'my ', 'me ', 'mine ', "I'm", "I've"]
        if any(fp in summary.lower() for fp in first_person):
            summary_issues.append("Avoid first-person pronouns (I, my, etc.)")

        if summary_issues:
            suggestions['summary'] = summary_issues

    # Check experience bullets
    experiences = job_data.get('experiences', [])
    for i, exp in enumerate(experiences):
        bullets = exp.get('bullets', [])
        exp_issues = []

        if len(bullets) < 2:
            exp_issues.append(f"Experience {i+1}: Add at least 2-3 bullets")

        for j, bullet in enumerate(bullets):
            # Check for numbers/metrics
            has_number = any(char.isdigit() for char in bullet)
            if not has_number:
                exp_issues.append(f"Bullet {i+1}.{j+1}: Add quantifiable metrics")

            # Check for first-person
            if any(fp in bullet.lower() for fp in first_person):
                exp_issues.append(f"Bullet {i+1}.{j+1}: Remove first-person pronouns")

        if exp_issues:
            suggestions[f'experience_{i+1}'] = exp_issues

    return suggestions


def _fallback_summary(basics: Dict, skills: List[str], experiences: List[Dict]) -> str:
    """
    Generate a basic summary without AI (fallback).
    """
    title = basics.get('title', 'professional').strip()

    pieces = []

    # Opening
    if experiences:
        company = experiences[-1].get('company', '').strip()
        if company:
            pieces.append(f"{title.capitalize()} with hands-on experience at {company}.")
        else:
            pieces.append(f"Experienced {title.lower()} with proven track record.")
    else:
        pieces.append(f"{title.capitalize()} with strong technical foundation.")

    # Skills
    if skills:
        top_skills = skills[:3]
        pieces.append(f"Skilled in {', '.join(top_skills)}.")

    # Generic strength
    pieces.append("Delivering reliable results and driving project success.")

    return " ".join(pieces)


def batch_enhance_content(job_data: Dict) -> Dict:
    """
    Enhance all content in a job (summary + bullets) in one go.
    Useful for final polish before rendering.

    Args:
        job_data: Full job answers dict

    Returns:
        Enhanced job_data dict
    """
    if not _claude_client:
        logger.warning("[orchestrator] No AI available for batch enhancement")
        return job_data

    enhanced = job_data.copy()

    # Enhance summary
    basics = job_data.get('basics', {})
    skills = job_data.get('skills', [])
    experiences = job_data.get('experiences', [])

    if basics and not job_data.get('summary'):
        # Auto-generate if missing
        enhanced['summary'] = enhance_summary(basics, skills, experiences)
    elif job_data.get('summary'):
        # Enhance existing
        enhanced['summary'] = enhance_summary(basics, skills, experiences)

    # Enhance experience bullets
    enhanced_exps = []
    for exp in experiences:
        enhanced_exp = exp.copy()
        bullets = exp.get('bullets', [])
        enhanced_bullets = []

        role = exp.get('role', '')
        company = exp.get('company', '')

        for bullet in bullets:
            enhanced_bullets.append(enhance_bullet(bullet, role, company))

        enhanced_exp['bullets'] = enhanced_bullets
        enhanced_exps.append(enhanced_exp)

    enhanced['experiences'] = enhanced_exps

    logger.info("[orchestrator] Batch enhancement complete")
    return enhanced
