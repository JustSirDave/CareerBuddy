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
    Generate CV with exact layout from reference template.
    Single-page, clean, professional document with:
    - Centered header (name, title, contact details on one line)
    - Profiles section (horizontal layout)
    - Summary paragraph
    - Experience with right-aligned dates
    - Education
    - References
    - Skills in two columns
    """
    answers = job.answers or {}
    doc = Document()

    # Set document margins (narrow margins for single-page)
    sections = doc.sections
    for section in sections:
        section.top_margin = Inches(0.5)
        section.bottom_margin = Inches(0.5)
        section.left_margin = Inches(0.7)
        section.right_margin = Inches(0.7)

    # Get data
    basics = answers.get('basics', {})
    profiles = answers.get('profiles', [])
    summary = answers.get('summary', '')
    skills = answers.get('skills', [])
    experiences = answers.get('experiences', [])
    education = answers.get('education', [])
    references = answers.get('references', [])

    # ==================== HEADER ====================
    name = basics.get('name', 'Your Name')
    title = basics.get('title', 'Professional Title')

    # Name (Large, Bold, Centered)
    name_para = doc.add_paragraph()
    name_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    name_run = name_para.add_run(name)
    name_run.font.size = Pt(20)
    name_run.font.bold = True
    name_run.font.name = 'Arial'
    name_para.space_after = Pt(2)

    # Title (Centered, smaller)
    title_para = doc.add_paragraph()
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title_para.add_run(title)
    title_run.font.size = Pt(11)
    title_run.font.name = 'Arial'
    title_para.space_after = Pt(2)

    # Contact Info - Single line with separators
    contact_parts = []
    if basics.get('location'):
        contact_parts.append(f"📍 {basics['location']}")
    if basics.get('phone'):
        contact_parts.append(f"📞 {basics['phone']}")
    if basics.get('email'):
        contact_parts.append(f"✉ {basics['email']}")

    if contact_parts:
        contact_para = doc.add_paragraph()
        contact_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        contact_run = contact_para.add_run('     '.join(contact_parts))
        contact_run.font.size = Pt(9)
        contact_run.font.name = 'Arial'
        contact_para.space_after = Pt(6)

    # ==================== PROFILES ====================
    if profiles:
        _add_cv_section_heading(doc, 'Profiles')
        
        profiles_para = doc.add_paragraph()
        profiles_para.alignment = WD_ALIGN_PARAGRAPH.LEFT
        
        profile_texts = []
        for profile in profiles:
            platform = profile.get('platform', 'Profile')
            url = profile.get('url', '')
            if platform and url:
                profile_texts.append(f"🔗 {platform}: {url}")
        
        if profile_texts:
            profile_run = profiles_para.add_run('     '.join(profile_texts))
            profile_run.font.size = Pt(10)
            profile_run.font.name = 'Arial'
        
        doc.add_paragraph().space_after = Pt(4)

    # ==================== SUMMARY ====================
    if summary:
        _add_cv_section_heading(doc, 'Summary')
        summary_para = doc.add_paragraph(summary)
        summary_para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        _set_body_font(summary_para)
        doc.add_paragraph().space_after = Pt(4)

    # ==================== EXPERIENCE ====================
    if experiences:
        _add_cv_section_heading(doc, 'Experience')

        for exp in experiences:
            # Company name (bold, left) and dates (right) on same line
            exp_header = doc.add_paragraph()
            exp_header.paragraph_format.space_after = Pt(0)
            
            # Company name (bold)
            company = exp.get('company', 'Company Name')
            company_run = exp_header.add_run(company)
            company_run.font.bold = True
            company_run.font.size = Pt(11)
            company_run.font.name = 'Arial'
            
            # Add dates on the same line (right-aligned)
            date_str = ''
            if exp.get('start'):
                date_str = exp['start']
                if exp.get('end'):
                    date_str += f" - {exp['end']}"
            
            if date_str:
                # Add tab stop for right alignment
                from docx.shared import Pt as PT
                from docx.enum.text import WD_TAB_ALIGNMENT
                tab_stops = exp_header.paragraph_format.tab_stops
                tab_stops.add_tab_stop(Inches(6.0), WD_TAB_ALIGNMENT.RIGHT)
                
                exp_header.add_run('\t')
                date_run = exp_header.add_run(date_str)
                date_run.font.size = Pt(10)
                date_run.font.name = 'Arial'
            
            # Job title (left) and location (right) on next line
            role_para = doc.add_paragraph()
            role_para.paragraph_format.space_after = Pt(0)
            
            role = exp.get('role', 'Job Title')
            role_run = role_para.add_run(role)
            role_run.font.size = Pt(10)
            role_run.font.name = 'Arial'
            
            location = exp.get('location', '')
            if location:
                from docx.enum.text import WD_TAB_ALIGNMENT
                tab_stops = role_para.paragraph_format.tab_stops
                tab_stops.add_tab_stop(Inches(6.0), WD_TAB_ALIGNMENT.RIGHT)
                
                role_para.add_run('\t')
                loc_run = role_para.add_run(location)
                loc_run.font.size = Pt(10)
                loc_run.font.name = 'Arial'
            
            # Bullets/description
            bullets = exp.get('bullets', [])
            if bullets:
                for bullet in bullets:
                    bullet_para = doc.add_paragraph()
                    bullet_para.paragraph_format.left_indent = Inches(0)
                    bullet_para.paragraph_format.space_after = Pt(2)
                    bullet_run = bullet_para.add_run(bullet)
                    bullet_run.font.size = Pt(10)
                    bullet_run.font.name = 'Arial'
            
            # Spacing between experiences
            doc.add_paragraph().space_after = Pt(6)

    # ==================== EDUCATION ====================
    if education:
        _add_cv_section_heading(doc, 'Education')

        for edu in education:
            # Institution name (bold, left) and years (right)
            edu_header = doc.add_paragraph()
            edu_header.paragraph_format.space_after = Pt(0)
            
            institution = edu.get('institution', 'Institution Name')
            inst_run = edu_header.add_run(institution)
            inst_run.font.bold = True
            inst_run.font.size = Pt(11)
            inst_run.font.name = 'Arial'
            
            # Years on right
            years = edu.get('years', '')
            if years:
                from docx.enum.text import WD_TAB_ALIGNMENT
                tab_stops = edu_header.paragraph_format.tab_stops
                tab_stops.add_tab_stop(Inches(6.0), WD_TAB_ALIGNMENT.RIGHT)
                
                edu_header.add_run('\t')
                years_run = edu_header.add_run(years)
                years_run.font.size = Pt(10)
                years_run.font.name = 'Arial'
            
            # Degree (left) and degree type (right)
            degree_para = doc.add_paragraph()
            degree_para.paragraph_format.space_after = Pt(2)
            
            degree = edu.get('degree', '')
            degree_run = degree_para.add_run(degree)
            degree_run.font.size = Pt(10)
            degree_run.font.name = 'Arial'
            
            degree_type = edu.get('degree_type', '')
            if degree_type:
                from docx.enum.text import WD_TAB_ALIGNMENT
                tab_stops = degree_para.paragraph_format.tab_stops
                tab_stops.add_tab_stop(Inches(6.0), WD_TAB_ALIGNMENT.RIGHT)
                
                degree_para.add_run('\t')
                type_run = degree_para.add_run(degree_type)
                type_run.font.size = Pt(10)
                type_run.font.name = 'Arial'
        
        doc.add_paragraph().space_after = Pt(4)

    # ==================== REFERENCES ====================
    if references:
        _add_cv_section_heading(doc, 'References')

        for ref in references:
            # Name (bold)
            ref_name = ref.get('name', 'Reference Name')
            name_para = doc.add_paragraph()
            name_para.paragraph_format.space_after = Pt(0)
            name_run = name_para.add_run(ref_name)
            name_run.font.bold = True
            name_run.font.size = Pt(10)
            name_run.font.name = 'Arial'
            
            # Title/role
            ref_title = ref.get('title', '')
            if ref_title:
                title_para = doc.add_paragraph(ref_title)
                title_para.paragraph_format.space_after = Pt(0)
                _set_body_font(title_para)
            
            # Organization
            ref_org = ref.get('organization', '')
            if ref_org:
                org_para = doc.add_paragraph(ref_org)
                org_para.paragraph_format.space_after = Pt(6)
                _set_body_font(org_para)
        
        doc.add_paragraph().space_after = Pt(4)

    # ==================== SKILLS ====================
    if skills:
        from docx.oxml.shared import OxmlElement
        from docx.oxml.ns import qn
        
        _add_cv_section_heading(doc, 'Skills')
        
        # Create two-column layout using table (hidden borders)
        num_skills = len(skills)
        rows_needed = (num_skills + 1) // 2  # Ceiling division
        
        table = doc.add_table(rows=rows_needed, cols=2)
        table.style = 'Table Grid'
        
        # Remove borders
        for row in table.rows:
            for cell in row.cells:
                # Set cell border to none
                tcPr = cell._element.get_or_add_tcPr()
                tcBorders = OxmlElement('w:tcBorders')
                for border_name in ['top', 'left', 'bottom', 'right', 'insideH', 'insideV']:
                    border = OxmlElement(f'w:{border_name}')
                    border.set(qn('w:val'), 'none')
                    tcBorders.append(border)
                tcPr.append(tcBorders)
        
        # Fill in skills
        for idx, skill in enumerate(skills):
            row_idx = idx // 2
            col_idx = idx % 2
            cell = table.rows[row_idx].cells[col_idx]
            cell.text = skill
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(10)
                    run.font.name = 'Arial'

    # Save to bytes
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    logger.info(f"[renderer] Generated CV DOCX for job.id={job.id}")
    return buffer.getvalue()


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


def _add_cv_section_heading(doc: Document, text: str):
    """Add a CV section heading with horizontal line separator"""
    heading = doc.add_paragraph()
    heading.paragraph_format.space_before = Pt(6)
    heading.paragraph_format.space_after = Pt(4)
    heading_run = heading.add_run(text)
    heading_run.font.bold = True
    heading_run.font.size = Pt(11)
    heading_run.font.name = 'Arial'
    heading_run.font.color.rgb = RGBColor(0, 0, 0)

    # Add bottom border (horizontal line)
    from docx.oxml.shared import OxmlElement
    from docx.oxml.ns import qn

    pPr = heading._element.get_or_add_pPr()
    pBdr = OxmlElement('w:pBdr')
    bottom = OxmlElement('w:bottom')
    bottom.set(qn('w:val'), 'single')
    bottom.set(qn('w:sz'), '4')  # Thinner border
    bottom.set(qn('w:space'), '1')
    bottom.set(qn('w:color'), '000000')
    pBdr.append(bottom)
    pPr.append(pBdr)


def _set_body_font(paragraph):
    """Set consistent body text formatting"""
    for run in paragraph.runs:
        run.font.name = 'Arial'
        run.font.size = Pt(10)
