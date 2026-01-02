"""
Document rendering service - Generate professional DOCX and PDF files
"""
from io import BytesIO
from typing import Dict, List
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from loguru import logger

from app.models import Job


def render_resume(job: Job) -> bytes:
    """
    Generate ATS-compliant DOCX resume from job data.
    Follows rules from rules/ats.json:
    - No tables or icons
    - Standard fonts (Arial)
    - Simple formatting
    - Dates in MMM YYYY format
    """
    answers = job.answers or {}
    doc = Document()

    # Set document margins (1 inch all around)
    sections = doc.sections
    for section in sections:
        section.top_margin = Inches(0.5)
        section.bottom_margin = Inches(0.5)
        section.left_margin = Inches(0.75)
        section.right_margin = Inches(0.75)

    # Get data
    basics = answers.get('basics', {})
    summary = answers.get('summary', '')
    skills = answers.get('skills', [])
    experiences = answers.get('experiences', [])
    education = answers.get('education', [])
    projects = answers.get('projects', [])

    # ==================== HEADER ====================
    name = basics.get('name', 'Your Name')
    title = basics.get('title', 'Professional Title')

    # Name (Large, Bold)
    name_para = doc.add_paragraph()
    name_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    name_run = name_para.add_run(name)
    name_run.font.size = Pt(18)
    name_run.font.bold = True
    name_run.font.name = 'Arial'

    # Title
    title_para = doc.add_paragraph()
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title_para.add_run(title)
    title_run.font.size = Pt(12)
    title_run.font.name = 'Arial'

    # Contact Info
    contact_parts = []
    if basics.get('email'):
        contact_parts.append(basics['email'])
    if basics.get('phone'):
        contact_parts.append(basics['phone'])
    if basics.get('location'):
        contact_parts.append(basics['location'])

    if contact_parts:
        contact_para = doc.add_paragraph()
        contact_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        contact_run = contact_para.add_run(' | '.join(contact_parts))
        contact_run.font.size = Pt(10)
        contact_run.font.name = 'Arial'

    # Add spacing after header
    doc.add_paragraph()

    # ==================== SUMMARY ====================
    if summary:
        _add_section_heading(doc, 'PROFESSIONAL SUMMARY')
        summary_para = doc.add_paragraph(summary)
        _set_body_font(summary_para)
        doc.add_paragraph()  # Spacing

    # ==================== SKILLS ====================
    if skills:
        _add_section_heading(doc, 'SKILLS')
        skills_text = ', '.join(skills)
        skills_para = doc.add_paragraph(skills_text)
        _set_body_font(skills_para)
        doc.add_paragraph()  # Spacing

    # ==================== EXPERIENCE ====================
    if experiences:
        _add_section_heading(doc, 'PROFESSIONAL EXPERIENCE')

        for i, exp in enumerate(experiences):
            # Job Title & Company
            title_line = doc.add_paragraph()
            title_run = title_line.add_run(exp.get('role', 'Role'))
            title_run.font.bold = True
            title_run.font.size = Pt(11)
            title_run.font.name = 'Arial'

            # Company, Location | Dates
            info_parts = []
            if exp.get('company'):
                info_parts.append(exp['company'])
            if exp.get('location'):
                info_parts.append(exp['location'])

            info_line = ' | '.join(info_parts)

            # Add dates
            date_part = ''
            if exp.get('start'):
                date_part = exp['start']
                if exp.get('end'):
                    date_part += f" - {exp['end']}"

            if date_part:
                info_line += f" | {date_part}"

            if info_line:
                info_para = doc.add_paragraph(info_line)
                _set_body_font(info_para)

            # Bullets
            bullets = exp.get('bullets', [])
            for bullet in bullets:
                bullet_para = doc.add_paragraph(bullet, style='List Bullet')
                _set_body_font(bullet_para)

            # Add spacing between experiences (except last one)
            if i < len(experiences) - 1:
                doc.add_paragraph()

        doc.add_paragraph()  # Section spacing

    # ==================== EDUCATION ====================
    if education:
        _add_section_heading(doc, 'EDUCATION')

        for edu in education:
            edu_details = edu.get('details', '')
            if edu_details:
                edu_para = doc.add_paragraph(edu_details)
                _set_body_font(edu_para)

        doc.add_paragraph()  # Spacing

    # ==================== PROJECTS ====================
    if projects:
        _add_section_heading(doc, 'PROJECTS & CERTIFICATIONS')

        for proj in projects:
            proj_details = proj.get('details', '')
            if proj_details:
                proj_para = doc.add_paragraph(proj_details, style='List Bullet')
                _set_body_font(proj_para)

    # Save to bytes
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    logger.info(f"[renderer] Generated resume DOCX for job.id={job.id}")
    return buffer.getvalue()


def render_cv(job: Job) -> bytes:
    """
    Generate CV (same as resume for now, can be customized later)
    CV typically includes more detail: publications, research, etc.
    """
    # For now, use same renderer as resume
    # TODO: Add CV-specific sections (Publications, Research, etc.)
    return render_resume(job)


def render_cover_letter(job: Job) -> bytes:
    """
    Generate cover letter DOCX
    """
    answers = job.answers or {}
    basics = answers.get("basics", {})
    role = answers.get("cover_role") or answers.get("target_role") or "the role"
    company = answers.get("cover_company", "your company")
    highlights = answers.get("cover_highlights", [])
    summary = answers.get("summary", "")

    doc = Document()

    # Set margins
    for section in doc.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)

    # Header
    header_lines = []
    name = basics.get("name")
    if name:
        header_lines.append(name)
    contact_parts = [part for part in [basics.get("email"), basics.get("phone"), basics.get("location")] if part]
    if contact_parts:
        header_lines.append(" | ".join(contact_parts))

    for line in header_lines:
        para = doc.add_paragraph(line)
        para.alignment = WD_ALIGN_PARAGRAPH.LEFT
        _set_body_font(para)

    doc.add_paragraph()  # spacer

    # Greeting
    greet = f"Dear Hiring Manager{f' at {company}' if company else ''},"
    greet_para = doc.add_paragraph(greet)
    _set_body_font(greet_para)

    # Opening
    opening = f"I am excited to apply for the {role} position at {company}."
    opening_para = doc.add_paragraph(opening)
    _set_body_font(opening_para)

    # Summary / pitch
    if summary:
        summary_para = doc.add_paragraph(summary)
        _set_body_font(summary_para)

    # Highlights
    if highlights:
        highlights_intro = doc.add_paragraph("Selected achievements:")
        _set_body_font(highlights_intro)
        for h in highlights:
            bullet = doc.add_paragraph(h, style="List Bullet")
            _set_body_font(bullet)

    # Closing
    closing_lines = [
        "I would welcome the opportunity to discuss how my experience aligns with your needs.",
        "Thank you for your time and consideration.",
        "",
        "Sincerely,"
    ]
    for line in closing_lines:
        para = doc.add_paragraph(line)
        _set_body_font(para)

    if name:
        sign = doc.add_paragraph(name)
        _set_body_font(sign)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    logger.info(f"[renderer] Generated cover letter DOCX for job.id={job.id}")
    return buffer.getvalue()


def render_revamp(job: Job) -> bytes:
    """
    Generate a DOCX file from AI-revamped resume content (free-form text).
    """
    answers = job.answers or {}
    improved_text = answers.get("revamped_content") or answers.get("original_content") or ""

    doc = Document()

    # Margins
    for section in doc.sections:
        section.top_margin = Inches(0.75)
        section.bottom_margin = Inches(0.75)
        section.left_margin = Inches(0.75)
        section.right_margin = Inches(0.75)

    _add_section_heading(doc, "IMPROVED RESUME CONTENT")

    if not improved_text:
        para = doc.add_paragraph("No content provided.")
        _set_body_font(para)
    else:
        for line in improved_text.splitlines():
            if not line.strip():
                doc.add_paragraph()
                continue
            para = doc.add_paragraph(line.strip())
            _set_body_font(para)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    logger.info(f"[renderer] Generated revamped DOCX for job.id={job.id}")
    return buffer.getvalue()


def _add_section_heading(doc: Document, text: str):
    """Add a section heading with consistent styling"""
    heading = doc.add_paragraph()
    heading_run = heading.add_run(text)
    heading_run.font.bold = True
    heading_run.font.size = Pt(12)
    heading_run.font.name = 'Arial'
    heading_run.font.color.rgb = RGBColor(0, 0, 0)

    # Add bottom border
    from docx.oxml.shared import OxmlElement
    from docx.oxml.ns import qn

    pPr = heading._element.get_or_add_pPr()
    pBdr = OxmlElement('w:pBdr')
    bottom = OxmlElement('w:bottom')
    bottom.set(qn('w:val'), 'single')
    bottom.set(qn('w:sz'), '6')  # Border width
    bottom.set(qn('w:space'), '1')
    bottom.set(qn('w:color'), '000000')
    pBdr.append(bottom)
    pPr.append(pBdr)


def _set_body_font(paragraph):
    """Set consistent body text formatting"""
    for run in paragraph.runs:
        run.font.name = 'Arial'
        run.font.size = Pt(10)
