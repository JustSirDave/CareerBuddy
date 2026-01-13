"""
PDF rendering service - Generate PDFs directly from data using ReportLab
This bypasses DOCX->PDF conversion issues with LibreOffice
"""
from io import BytesIO
from typing import Dict, List
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from loguru import logger


def render_template_1_pdf(answers: dict) -> bytes:
    """
    Generate PDF directly for Template 1 using ReportLab
    Matches the exact layout of the DOCX version with table structure
    """
    buffer = BytesIO()
    
    # Create PDF with custom margins (0.5 inch all around)
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.5*inch,
        leftMargin=0.5*inch,
        topMargin=0.5*inch,
        bottomMargin=0.5*inch
    )
    
    # Extract data
    basics = answers.get('basics', {})
    summary = answers.get('summary', '')
    experiences = answers.get('experiences', [])
    education = answers.get('education', [])
    skills = answers.get('skills', [])
    profiles = answers.get('profiles', [])
    projects = answers.get('projects', [])
    references = answers.get('references', [])
    
    # Clean skills
    skills = [s.strip() for s in skills if s and isinstance(s, str) and not s.strip().isdigit() and len(s.strip()) > 1]
    
    # Build document elements
    story = []
    styles = getSampleStyleSheet()
    
    # Define custom styles to match DOCX
    name_style = ParagraphStyle(
        'NameStyle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.black,
        spaceAfter=0,
        spaceBefore=0,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Normal'],
        fontSize=14,
        textColor=colors.black,
        spaceAfter=0,
        spaceBefore=0,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    contact_style = ParagraphStyle(
        'ContactStyle',
        parent=styles['Normal'],
        fontSize=13,
        textColor=colors.black,
        spaceAfter=10,
        spaceBefore=0,
        alignment=TA_CENTER,
        fontName='Helvetica'
    )
    
    label_style = ParagraphStyle(
        'LabelStyle',
        parent=styles['Normal'],
        fontSize=14,
        textColor=colors.black,
        spaceAfter=0,
        spaceBefore=0,
        fontName='Helvetica-Bold',
        leading=16
    )
    
    content_style = ParagraphStyle(
        'ContentStyle',
        parent=styles['Normal'],
        fontSize=12,
        textColor=colors.black,
        spaceAfter=0,
        spaceBefore=0,
        fontName='Helvetica',
        leading=14
    )
    
    content_small_style = ParagraphStyle(
        'ContentSmallStyle',
        parent=styles['Normal'],
        fontSize=12,
        textColor=colors.black,
        spaceAfter=2,
        spaceBefore=2,
        fontName='Helvetica',
        leading=14,
        leftIndent=0.2*inch,
        firstLineIndent=-0.15*inch
    )
    
    # ==================== HEADER ====================
    name = basics.get('name', 'Your Name')
    story.append(Paragraph(name.title(), name_style))
    story.append(Spacer(1, 2))
    
    # Check multiple possible locations for job title
    job_title = basics.get('title', '') or basics.get('job_title', '') or answers.get('target_role', '')
    if job_title:
        story.append(Paragraph(job_title.upper(), title_style))
        story.append(Spacer(1, 4))
    
    # Contact info (one line with location first)
    contact_parts = []
    
    # Add location first if available
    location = basics.get('location', '')
    if not location:
        city = basics.get('city', '')
        country = basics.get('country', '')
        location = f"{city}, {country}" if city and country else city or country
    
    if location:
        contact_parts.append(location)
    
    phone = basics.get('phone', '')
    if phone:
        contact_parts.append(phone)
    
    email = basics.get('email', '')
    if email:
        contact_parts.append(email)
    
    if contact_parts:
        contact_text = " | ".join(contact_parts)
        story.append(Paragraph(contact_text, contact_style))
    
    # Horizontal line separator (full width, clean line)
    from reportlab.platypus import HRFlowable
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.black, spaceBefore=0, spaceAfter=12))
    
    # ==================== BUILD TABLE FOR CONTENT ====================
    table_data = []
    
    # PROFILES
    if profiles:
        profile_links = []
        for profile in profiles:
            platform = profile.get('platform', 'Profile')
            url = profile.get('url', '')
            if platform and url:
                profile_links.append(f'<link href="{url}" color="blue"><u>{platform}</u></link>')
        
        if profile_links:
            label = Paragraph('<b>Profiles</b>', label_style)
            content = Paragraph(' | '.join(profile_links), content_style)
            table_data.append([label, content])
    
    # SUMMARY
    if summary:
        label = Paragraph('<b>Summary</b>', label_style)
        content = Paragraph(summary, content_style)
        table_data.append([label, content])
    
    # EXPERIENCE - Using nested tables for proper alignment
    if experiences:
        label = Paragraph('<b>Experience</b>', label_style)
        
        # Create nested content for each experience
        exp_elements = []
        for idx, exp in enumerate(experiences):
            company = exp.get('company', 'Company Name')
            title = exp.get('title', exp.get('role', ''))
            start = exp.get('start', '')
            end = exp.get('end', '')
            location = exp.get('city', exp.get('location', ''))
            bullets = exp.get('bullets', [])
            
            # Company and date on same line (mini table)
            date_str = f"{start} - {end}" if start and end else start or end
            company_date_data = [[
                Paragraph(f"<b>{company}</b>", content_style),
                Paragraph(f"<b><i>{date_str}</i></b>" if date_str else "", content_style)
            ]]
            company_date_table = Table(company_date_data, colWidths=[4.5*inch, 1.8*inch])
            company_date_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ]))
            exp_elements.append(company_date_table)
            
            # Title and location on same line (mini table)
            if title:
                title_loc_data = [[
                    Paragraph(title, content_style),
                    Paragraph(location if location else "", content_style)
                ]]
                title_loc_table = Table(title_loc_data, colWidths=[4.5*inch, 1.8*inch])
                title_loc_table.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                    ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                    ('TOPPADDING', (0, 0), (-1, -1), 2),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ]))
                exp_elements.append(title_loc_table)
            
            # Bullets - with proper formatting and currency handling
            for bullet in bullets:
                # Replace Naira symbol with readable text
                bullet_text = bullet.replace('₦', 'N').replace('■', 'N')
                exp_elements.append(Paragraph(f"• {bullet_text}", content_small_style))
            
            # Spacing between experiences
            if idx < len(experiences) - 1:
                exp_elements.append(Spacer(1, 8))
        
        # Wrap all experience elements in a single cell
        table_data.append([label, exp_elements])
    
    # EDUCATION - Using nested tables for proper alignment
    if education:
        label = Paragraph('<b>Education</b>', label_style)
        
        edu_elements = []
        for idx, edu in enumerate(education):
            institution = edu.get('institution', 'Institution')
            degree = edu.get('degree', '')
            degree_type = edu.get('degree_type', '')
            years = edu.get('years', '')
            
            # Institution and year on same line (mini table)
            inst_year_data = [[
                Paragraph(f"<b>{institution}</b>", content_style),
                Paragraph(f"<b>{years}</b>" if years else "", content_style)
            ]]
            inst_year_table = Table(inst_year_data, colWidths=[4.5*inch, 1.8*inch])
            inst_year_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ]))
            edu_elements.append(inst_year_table)
            
            # Degree and degree type on same line (mini table)
            if degree or degree_type:
                deg_type_data = [[
                    Paragraph(degree if degree else "", content_style),
                    Paragraph(degree_type if degree_type else "", content_style)
                ]]
                deg_type_table = Table(deg_type_data, colWidths=[4.5*inch, 1.8*inch])
                deg_type_table.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                    ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                    ('TOPPADDING', (0, 0), (-1, -1), 2),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ]))
                edu_elements.append(deg_type_table)
            
            # Spacing between education entries
            if idx < len(education) - 1:
                edu_elements.append(Spacer(1, 8))
        
        table_data.append([label, edu_elements])
    
    # PROJECTS
    if projects:
        label = Paragraph('<b>Projects</b>', label_style)
        proj_paras = []
        proj_style = ParagraphStyle(
            'ProjectStyle',
            parent=content_small_style,
            leftIndent=0.2*inch,
            firstLineIndent=-0.15*inch
        )
        for proj in projects:
            details = proj.get('details', '')
            if details:
                # Replace currency symbols
                details = details.replace('₦', 'N').replace('■', 'N')
                proj_paras.append(Paragraph(f"• {details}", proj_style))
        table_data.append([label, proj_paras])
    
    # SKILLS - Using nested table for 2-column layout
    if skills:
        label = Paragraph('<b>Skills</b>', label_style)
        
        # Create 2-column skills table
        skills_per_col = (len(skills) + 1) // 2
        col1 = skills[:skills_per_col]
        col2 = skills[skills_per_col:]
        
        skills_table_data = []
        for i in range(max(len(col1), len(col2))):
            row = []
            if i < len(col1):
                row.append(Paragraph(f"<b>{col1[i]}</b>", content_style))
            else:
                row.append(Paragraph("", content_style))
            
            if i < len(col2):
                row.append(Paragraph(f"<b>{col2[i]}</b>", content_style))
            else:
                row.append(Paragraph("", content_style))
            
            skills_table_data.append(row)
        
        skills_table = Table(skills_table_data, colWidths=[3.15*inch, 3.15*inch])
        skills_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        
        table_data.append([label, skills_table])
    
    # Create the main table
    if table_data:
        main_table = Table(table_data, colWidths=[1.2*inch, 6.3*inch])
        main_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ]))
        story.append(main_table)
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    
    logger.info("[pdf_renderer] Generated PDF with template_1")
    return buffer.getvalue()


def render_template_2_pdf(answers: dict) -> bytes:
    """
    Generate PDF directly for Template 2 (Modern Minimal) using ReportLab
    Features: Centered header, dark blue accents, clean contemporary design
    """
    buffer = BytesIO()
    
    # Create PDF with 0.5 inch margins
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.5*inch,
        leftMargin=0.5*inch,
        topMargin=0.5*inch,
        bottomMargin=0.5*inch
    )
    
    # Extract data
    basics = answers.get('basics', {})
    summary = answers.get('summary', '')
    experiences = answers.get('experiences', [])
    education = answers.get('education', [])
    skills = answers.get('skills', [])
    profiles = answers.get('profiles', [])
    certifications = answers.get('certifications', [])
    projects = answers.get('projects', [])
    
    # Clean skills
    skills = [s.strip() for s in skills if s and isinstance(s, str) and not s.strip().isdigit() and len(s.strip()) > 1][:6]
    
    # Build document elements
    story = []
    styles = getSampleStyleSheet()
    
    # Dark blue color for accents
    dark_blue = colors.Color(0/255, 51/255, 102/255)
    
    # Define custom styles for Template 2
    name_style = ParagraphStyle(
        'NameStyle',
        parent=styles['Heading1'],
        fontSize=26,
        textColor=dark_blue,
        spaceAfter=2,
        spaceBefore=0,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Normal'],
        fontSize=13,
        textColor=colors.Color(80/255, 80/255, 80/255),
        spaceAfter=2,
        spaceBefore=0,
        alignment=TA_CENTER,
        fontName='Helvetica'
    )
    
    contact_style = ParagraphStyle(
        'ContactStyle',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.Color(60/255, 60/255, 60/255),
        spaceAfter=16,
        spaceBefore=0,
        alignment=TA_CENTER,
        fontName='Helvetica'
    )
    
    heading_style = ParagraphStyle(
        'HeadingStyle',
        parent=styles['Normal'],
        fontSize=13,
        textColor=dark_blue,
        spaceAfter=6,
        spaceBefore=0,
        fontName='Helvetica-Bold'
    )
    
    content_style = ParagraphStyle(
        'ContentStyle',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.black,
        spaceAfter=2,
        spaceBefore=0,
        fontName='Helvetica',
        leading=14
    )
    
    bullet_style = ParagraphStyle(
        'BulletStyle',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.black,
        spaceAfter=2,
        spaceBefore=0,
        fontName='Helvetica',
        leading=13,
        leftIndent=0.2*inch,
        firstLineIndent=-0.15*inch
    )
    
    # ==================== HEADER ====================
    name = basics.get('name', 'Your Name')
    story.append(Paragraph(name.upper(), name_style))
    
    job_title = basics.get('title', '') or answers.get('target_role', '')
    if job_title:
        story.append(Paragraph(job_title, title_style))
    
    # Contact info
    contact_parts = []
    location = basics.get('location', '')
    if not location:
        city = basics.get('city', '')
        country = basics.get('country', '')
        location = f"{city}, {country}" if city and country else city or country
    if location:
        contact_parts.append(location)
    if basics.get('phone'):
        contact_parts.append(basics['phone'])
    if basics.get('email'):
        contact_parts.append(basics['email'])
    
    if contact_parts:
        story.append(Paragraph(' | '.join(contact_parts), contact_style))
    
    # Horizontal line
    from reportlab.platypus import HRFlowable
    story.append(HRFlowable(width="100%", thickness=1, color=colors.black, spaceBefore=0, spaceAfter=12))
    
    # ==================== PROFILES ====================
    if profiles:
        story.append(Paragraph('<b>PROFILES</b>', heading_style))
        profile_links = []
        for profile in profiles:
            platform = profile.get('platform', 'Profile')
            url = profile.get('url', '')
            if platform and url:
                profile_links.append(f'<link href="{url}" color="blue"><u>{platform}</u></link>')
        if profile_links:
            story.append(Paragraph(' | '.join(profile_links), content_style))
        story.append(Spacer(1, 14))
    
    # ==================== SUMMARY ====================
    if summary:
        story.append(Paragraph('<b>PROFESSIONAL SUMMARY</b>', heading_style))
        story.append(Paragraph(summary, content_style))
        story.append(Spacer(1, 14))
    
    # ==================== EXPERIENCE ====================
    if experiences:
        story.append(Paragraph('<b>WORK EXPERIENCE</b>', heading_style))
        for idx, exp in enumerate(experiences):
            company = exp.get('company', 'Company Name')
            title = exp.get('title', exp.get('role', ''))
            start = exp.get('start', '')
            end = exp.get('end', '')
            location = exp.get('city', exp.get('location', ''))
            bullets = exp.get('bullets', [])
            
            # Company (bold)
            story.append(Paragraph(f"<b>{company}</b>", content_style))
            
            # Title and date
            date_str = f"{start} - {end}" if start and end else start or end
            if title:
                title_date = f"{title}"
                if date_str:
                    title_date += f" | {date_str}"
                if location:
                    title_date += f" | {location}"
                story.append(Paragraph(f"<i>{title_date}</i>", content_style))
            
            # Bullets
            for bullet in bullets:
                bullet_text = bullet.replace('₦', 'N').replace('■', 'N')
                story.append(Paragraph(f"• {bullet_text}", bullet_style))
            
            if idx < len(experiences) - 1:
                story.append(Spacer(1, 10))
        story.append(Spacer(1, 14))
    
    # ==================== EDUCATION ====================
    if education:
        story.append(Paragraph('<b>EDUCATION</b>', heading_style))
        for edu in education:
            institution = edu.get('institution', 'Institution')
            degree = edu.get('degree', '')
            degree_type = edu.get('degree_type', '')
            years = edu.get('years', '')
            
            story.append(Paragraph(f"<b>{institution}</b>", content_style))
            
            deg_info = []
            if degree:
                deg_info.append(degree)
            if degree_type:
                deg_info.append(degree_type)
            if years:
                deg_info.append(years)
            
            if deg_info:
                story.append(Paragraph(f"<i>{' | '.join(deg_info)}</i>", content_style))
        story.append(Spacer(1, 14))
    
    # ==================== CERTIFICATIONS ====================
    if certifications:
        story.append(Paragraph('<b>CERTIFICATIONS</b>', heading_style))
        for cert in certifications:
            cert_name = cert.get('name', '')
            cert_body = cert.get('issuing_body', '')
            cert_year = cert.get('year', '')
            
            cert_text = cert_name
            if cert_body:
                cert_text += f", {cert_body}"
            if cert_year:
                cert_text += f", {cert_year}"
            story.append(Paragraph(f"• {cert_text}", bullet_style))
        story.append(Spacer(1, 14))
    
    # ==================== PROJECTS ====================
    if projects:
        story.append(Paragraph('<b>PROJECTS</b>', heading_style))
        for proj in projects:
            details = proj.get('details', '')
            if details:
                details = details.replace('₦', 'N').replace('■', 'N')
                story.append(Paragraph(f"• {details}", bullet_style))
        story.append(Spacer(1, 14))
    
    # ==================== SKILLS ====================
    if skills:
        story.append(Paragraph('<b>TECHNICAL SKILLS</b>', heading_style))
        skills_text = ' • '.join(f"<b>{skill}</b>" for skill in skills)
        story.append(Paragraph(skills_text, content_style))
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    
    logger.info("[pdf_renderer] Generated PDF with template_2")
    return buffer.getvalue()


def render_template_3_pdf(answers: dict) -> bytes:
    """
    Generate PDF directly for Template 3 (Executive Bold) using ReportLab
    Features: Left-aligned header, bold black sections, authoritative presence
    """
    buffer = BytesIO()
    
    # Create PDF with larger margins (0.75 inch) for executive presence
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.75*inch,
        leftMargin=0.75*inch,
        topMargin=0.75*inch,
        bottomMargin=0.75*inch
    )
    
    # Extract data
    basics = answers.get('basics', {})
    summary = answers.get('summary', '')
    experiences = answers.get('experiences', [])
    education = answers.get('education', [])
    skills = answers.get('skills', [])
    profiles = answers.get('profiles', [])
    certifications = answers.get('certifications', [])
    projects = answers.get('projects', [])
    
    # Clean skills
    skills = [s.strip() for s in skills if s and isinstance(s, str) and not s.strip().isdigit() and len(s.strip()) > 1][:6]
    
    # Build document elements
    story = []
    styles = getSampleStyleSheet()
    
    # Define custom styles for Template 3
    name_style = ParagraphStyle(
        'NameStyle',
        parent=styles['Heading1'],
        fontSize=28,
        textColor=colors.black,
        spaceAfter=4,
        spaceBefore=0,
        alignment=TA_LEFT,
        fontName='Helvetica-Bold'
    )
    
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Normal'],
        fontSize=14,
        textColor=colors.Color(60/255, 60/255, 60/255),
        spaceAfter=4,
        spaceBefore=0,
        alignment=TA_LEFT,
        fontName='Helvetica-Bold'
    )
    
    contact_style = ParagraphStyle(
        'ContactStyle',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.Color(80/255, 80/255, 80/255),
        spaceAfter=18,
        spaceBefore=0,
        alignment=TA_LEFT,
        fontName='Helvetica'
    )
    
    heading_style = ParagraphStyle(
        'HeadingStyle',
        parent=styles['Normal'],
        fontSize=14,
        textColor=colors.black,
        spaceAfter=8,
        spaceBefore=0,
        fontName='Helvetica-Bold'
    )
    
    content_style = ParagraphStyle(
        'ContentStyle',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.black,
        spaceAfter=2,
        spaceBefore=0,
        fontName='Helvetica',
        leading=14
    )
    
    bullet_style = ParagraphStyle(
        'BulletStyle',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.black,
        spaceAfter=2,
        spaceBefore=0,
        fontName='Helvetica',
        leading=13,
        leftIndent=0.2*inch,
        firstLineIndent=-0.15*inch
    )
    
    # ==================== HEADER ====================
    name = basics.get('name', 'Your Name')
    story.append(Paragraph(name.upper(), name_style))
    
    job_title = basics.get('title', '') or answers.get('target_role', '')
    if job_title:
        story.append(Paragraph(job_title.upper(), title_style))
    
    # Contact info
    contact_parts = []
    location = basics.get('location', '')
    if not location:
        city = basics.get('city', '')
        country = basics.get('country', '')
        location = f"{city}, {country}" if city and country else city or country
    if location:
        contact_parts.append(location)
    if basics.get('phone'):
        contact_parts.append(basics['phone'])
    if basics.get('email'):
        contact_parts.append(basics['email'])
    
    if contact_parts:
        story.append(Paragraph(' | '.join(contact_parts), contact_style))
    
    # Thick horizontal line
    from reportlab.platypus import HRFlowable
    story.append(HRFlowable(width="100%", thickness=2, color=colors.black, spaceBefore=0, spaceAfter=14))
    
    # ==================== PROFILES ====================
    if profiles:
        story.append(Paragraph('<b>PROFESSIONAL PROFILES</b>', heading_style))
        profile_links = []
        for profile in profiles:
            platform = profile.get('platform', 'Profile')
            url = profile.get('url', '')
            if platform and url:
                profile_links.append(f'<link href="{url}" color="blue"><u>{platform}</u></link>')
        if profile_links:
            story.append(Paragraph('  |  '.join(profile_links), content_style))
        story.append(Spacer(1, 16))
    
    # ==================== SUMMARY ====================
    if summary:
        story.append(Paragraph('<b>EXECUTIVE SUMMARY</b>', heading_style))
        story.append(Paragraph(summary, content_style))
        story.append(Spacer(1, 16))
    
    # ==================== EXPERIENCE ====================
    if experiences:
        story.append(Paragraph('<b>PROFESSIONAL EXPERIENCE</b>', heading_style))
        for idx, exp in enumerate(experiences):
            company = exp.get('company', 'Company Name')
            title = exp.get('title', exp.get('role', ''))
            start = exp.get('start', '')
            end = exp.get('end', '')
            location = exp.get('city', exp.get('location', ''))
            bullets = exp.get('bullets', [])
            
            # Company (bold, larger)
            story.append(Paragraph(f"<b>{company}</b>", content_style))
            
            # Title and date
            date_str = f"{start} - {end}" if start and end else start or end
            if title:
                title_date = f"{title}"
                if date_str:
                    title_date += f" | {date_str}"
                if location:
                    title_date += f" | {location}"
                story.append(Paragraph(f"<i>{title_date}</i>", content_style))
            
            # Bullets
            for bullet in bullets:
                bullet_text = bullet.replace('₦', 'N').replace('■', 'N')
                story.append(Paragraph(f"• {bullet_text}", bullet_style))
            
            if idx < len(experiences) - 1:
                story.append(Spacer(1, 12))
        story.append(Spacer(1, 16))
    
    # ==================== EDUCATION ====================
    if education:
        story.append(Paragraph('<b>EDUCATION & CREDENTIALS</b>', heading_style))
        for edu in education:
            institution = edu.get('institution', 'Institution')
            degree = edu.get('degree', '')
            degree_type = edu.get('degree_type', '')
            years = edu.get('years', '')
            
            story.append(Paragraph(f"<b>{institution}</b>", content_style))
            
            deg_info = []
            if degree:
                deg_info.append(degree)
            if degree_type:
                deg_info.append(degree_type)
            if years:
                deg_info.append(years)
            
            if deg_info:
                story.append(Paragraph(f"<i>{' | '.join(deg_info)}</i>", content_style))
        story.append(Spacer(1, 16))
    
    # ==================== CERTIFICATIONS ====================
    if certifications:
        story.append(Paragraph('<b>PROFESSIONAL CERTIFICATIONS</b>', heading_style))
        for cert in certifications:
            cert_name = cert.get('name', '')
            cert_body = cert.get('issuing_body', '')
            cert_year = cert.get('year', '')
            
            cert_text = cert_name
            if cert_body:
                cert_text += f", {cert_body}"
            if cert_year:
                cert_text += f", {cert_year}"
            story.append(Paragraph(f"• {cert_text}", bullet_style))
        story.append(Spacer(1, 16))
    
    # ==================== PROJECTS ====================
    if projects:
        story.append(Paragraph('<b>KEY PROJECTS</b>', heading_style))
        for proj in projects:
            details = proj.get('details', '')
            if details:
                details = details.replace('₦', 'N').replace('■', 'N')
                story.append(Paragraph(f"• {details}", bullet_style))
        story.append(Spacer(1, 16))
    
    # ==================== SKILLS ====================
    if skills:
        story.append(Paragraph('<b>CORE COMPETENCIES</b>', heading_style))
        skills_text = ' • '.join(f"<b>{skill}</b>" for skill in skills)
        story.append(Paragraph(skills_text, content_style))
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    
    logger.info("[pdf_renderer] Generated PDF with template_3")
    return buffer.getvalue()


def render_pdf_from_data(answers: dict, template: str) -> bytes:
    """
    Main entry point for PDF generation from data
    Routes to the appropriate template renderer
    """
    if template == 'template_1':
        return render_template_1_pdf(answers)
    elif template == 'template_2':
        return render_template_2_pdf(answers)
    elif template == 'template_3':
        return render_template_3_pdf(answers)
    else:
        raise ValueError(f"Unknown template: {template}")
