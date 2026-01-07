# CV Template Documentation

## Overview

This document describes the CV template implementation in CareerBuddy that faithfully replicates a specific professional CV layout. The template produces a single-page, clean, professional document suitable for academic and professional contexts.

## Template Structure

The CV follows this exact structure:

```
┌─────────────────────────────────────────────┐
│           CANDIDATE NAME (Centered)          │
│         Professional Title (Centered)        │
│    📍 Location  📞 Phone  ✉ Email           │
├─────────────────────────────────────────────┤
│ Profiles                                     │
│ 🔗 LinkedIn: url  🔗 Facebook: url          │
├─────────────────────────────────────────────┤
│ Summary                                      │
│ Paragraph describing personal traits...      │
├─────────────────────────────────────────────┤
│ Experience                                   │
│ Company Name (Bold)          Jun 2021 - May 2022│
│ Job Title                         City Name  │
│ • Responsibility description...              │
│                                              │
│ [Additional experiences...]                  │
├─────────────────────────────────────────────┤
│ Education                                    │
│ Institution Name (Bold)          2018-2024   │
│ Degree Title                 Degree Type     │
├─────────────────────────────────────────────┤
│ References                                   │
│ Reference Name (Bold)                        │
│ Title / Role                                 │
│ Organization                                 │
├─────────────────────────────────────────────┤
│ Skills                                       │
│ Skill 1          Skill 4                     │
│ Skill 2          Skill 5                     │
│ Skill 3          Skill 6                     │
└─────────────────────────────────────────────┘
```

## Data Structure

The CV renderer expects data in the following format:

### 1. Header Section (`basics`)

```python
"basics": {
    "name": "Full Name",              # Required - Displays at top, centered, large and bold
    "title": "Professional Title",     # Required - Displays below name, centered
    "location": "Address",             # Optional - With location icon
    "phone": "Phone Number",           # Optional - With phone icon
    "email": "email@example.com"       # Optional - With email icon
}
```

**Formatting:**
- Name: 20pt, bold, centered
- Title: 11pt, centered
- Contact: Single line, center-aligned, separated by spaces, 9pt

### 2. Profiles Section (`profiles`)

```python
"profiles": [
    {
        "platform": "LinkedIn",        # Platform name (e.g., LinkedIn, Facebook, GitHub)
        "url": "Profile Name or URL"   # Profile identifier or full URL
    }
]
```

**Formatting:**
- Horizontal layout with link icons
- Separated by spaces
- 10pt font

### 3. Summary Section (`summary`)

```python
"summary": "A single paragraph describing personal traits, work ethic, temperament, and suitability for the role. Should be descriptive, professional, and calm in tone."
```

**Formatting:**
- Single paragraph, justified alignment
- No bullet points
- 10pt font
- Describes personality, strengths, and suitability

### 4. Experience Section (`experiences`)

```python
"experiences": [
    {
        "company": "Company Name",     # Required - Bold, left-aligned
        "start": "Jun 2021",          # Required - Format: MMM YYYY
        "end": "May 2022",            # Required - Format: MMM YYYY or "Present"
        "role": "Job Title",          # Required - Regular font, left-aligned
        "location": "City Name",      # Optional - Right-aligned on same line as role
        "bullets": [                  # Optional - Description/responsibilities
            "Description of responsibilities and achievements..."
        ]
    }
]
```

**Formatting:**
- Company name (bold, 11pt) and dates (10pt) on same line
- Dates are right-aligned using tab stops at 6.0 inches
- Job title (10pt) and location (10pt) on next line
- Location is right-aligned
- Bullets or plain text for responsibilities (10pt)
- Consistent spacing between experiences

### 5. Education Section (`education`)

```python
"education": [
    {
        "institution": "University Name",  # Required - Bold, left-aligned
        "degree": "Degree Name",           # Required - Regular font, left-aligned
        "years": "2018-2024",             # Required - Right-aligned
        "degree_type": "Bachelor of..."   # Optional - Right-aligned on same line as degree
    }
]
```

**Formatting:**
- Institution name (bold, 11pt) and years (10pt) on same line
- Years are right-aligned using tab stops
- Degree title (10pt) and degree type (10pt) on next line
- Degree type is right-aligned

### 6. References Section (`references`)

```python
"references": [
    {
        "name": "Reference Full Name",     # Required - Bold
        "title": "Position / Role",        # Optional - Regular font
        "organization": "Organization"     # Optional - Regular font
    }
]
```

**Formatting:**
- Name in bold, 10pt
- Title and organization in regular 10pt
- Vertical layout (not inline)
- Spacing between references

### 7. Skills Section (`skills`)

```python
"skills": [
    "Skill 1",
    "Skill 2",
    "Skill 3",
    "Skill 4"
]
```

**Formatting:**
- Two-column layout using borderless table
- Short phrases (e.g., "Empathy", "Communication Skills")
- No proficiency bars or ratings
- 10pt font
- Even distribution across columns

## Formatting Rules

### Document Layout
- **Page Size:** Standard (8.5" × 11" or A4)
- **Margins:** 
  - Top/Bottom: 0.5 inches
  - Left/Right: 0.7 inches
- **Font:** Arial throughout
- **Colors:** Black text only (no colors beyond dark gray/black)

### Section Headers
- Bold, 11pt
- Horizontal line separator below each header
- Consistent spacing: 6pt before, 4pt after

### Alignment Rules
- Header (name, title, contact): Center-aligned
- Section content: Left-aligned
- Dates and locations: Right-aligned using tab stops at 6.0 inches
- Summary: Justified

### Spacing
- Minimal spacing for single-page layout
- Section headers: 6pt before, 4pt after
- Between items: 2-6pt depending on section
- No excessive whitespace

## Usage Example

```python
from app.models.job import Job
from app.services.renderer import render_cv

# Prepare CV data
cv_data = {
    "basics": {
        "name": "Jane Doe",
        "title": "Senior Educator",
        "location": "Lagos, Nigeria",
        "phone": "+234-123-456-789",
        "email": "jane.doe@email.com"
    },
    "profiles": [
        {"platform": "LinkedIn", "url": "jane-doe"}
    ],
    "summary": "Experienced educator with 10+ years...",
    "experiences": [...],
    "education": [...],
    "references": [...],
    "skills": ["Teaching", "Curriculum Design", ...]
}

# Create job with CV data
job = Job(answers=cv_data)

# Generate CV
cv_bytes = render_cv(job)

# Save to file
with open("output/cv.docx", "wb") as f:
    f.write(cv_bytes)
```

## Testing

Run the test script to generate a sample CV:

```bash
cd backend
python test_cv_generation.py
```

This will create `backend/output/test_cv_sample.docx` with sample data.

## Design Principles

1. **Faithful Replication:** The layout exactly matches the reference CV image
2. **No Modernization:** Maintains the original formatting style
3. **Single-Page Focus:** Optimized for single-page presentation
4. **Professional Tone:** Formal, minimal, academic-professional style
5. **ATS-Friendly:** Uses standard formatting without complex layouts

## Differences from Resume Template

| Feature | Resume Template | CV Template |
|---------|----------------|-------------|
| Layout | Dynamic spacing | Fixed single-page |
| Header | Left-aligned options | Always centered |
| Contacts | Vertical or horizontal | Always single line |
| Profiles | Not included | Dedicated section |
| References | Not included | Dedicated section |
| Skills | Comma-separated inline | Two-column table |
| Dates | Various formats | Right-aligned with tabs |
| Tone | Achievement-focused | Character-focused |

## Future Enhancements

Potential additions while maintaining the core layout:
- Publications section
- Research experience
- Languages section
- Awards and honors
- Professional memberships

## Technical Notes

- Uses `python-docx` library for DOCX generation
- Tab stops at 6.0 inches for right alignment
- Borderless tables for skills layout
- XML manipulation for section borders
- Space control using paragraph spacing properties

---

**Last Updated:** January 2, 2026  
**Version:** 1.0  
**Maintainer:** CareerBuddy Team



