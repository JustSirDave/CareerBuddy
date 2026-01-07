# CV Template Quick Start Guide

**Get started with the new CV template in 5 minutes.**

---

## ⚡ Quick Test

Generate a sample CV right now:

```bash
cd backend
python test_cv_generation.py
```

✅ Output: `backend/output/test_cv_sample.docx`

---

## 📋 Basic Usage

### Step 1: Prepare Your Data

```python
cv_data = {
    "basics": {
        "name": "Jane Doe",
        "title": "Senior Teacher",
        "location": "Lagos, Nigeria",
        "phone": "+234-123-456-789",
        "email": "jane@email.com"
    },
    "profiles": [
        {"platform": "LinkedIn", "url": "jane-doe"}
    ],
    "summary": "Experienced educator with strong leadership skills...",
    "experiences": [
        {
            "company": "School Name",
            "start": "Jan 2020",
            "end": "Present",
            "role": "Teacher",
            "location": "Lagos",
            "bullets": ["Taught 30+ students", "Improved test scores by 25%"]
        }
    ],
    "education": [
        {
            "institution": "University Name",
            "degree": "B.Ed. Education",
            "years": "2016-2020",
            "degree_type": "Bachelor of Education"
        }
    ],
    "references": [
        {
            "name": "Dr. Smith",
            "title": "Principal",
            "organization": "ABC School"
        }
    ],
    "skills": ["Teaching", "Leadership", "Communication"]
}
```

### Step 2: Generate CV

```python
from app.models.job import Job
from app.services.renderer import render_cv

# Assuming you have a Job object
job.answers = cv_data

# Generate
cv_bytes = render_cv(job)

# Save
with open("my_cv.docx", "wb") as f:
    f.write(cv_bytes)
```

---

## 🔗 Integration Options

### Option 1: Add to Existing Flow

If you already have resume generation:

```python
# In your router or service
if document_type == "cv":
    doc_bytes = render_cv(job)
elif document_type == "resume":
    doc_bytes = render_resume(job)
```

### Option 2: WhatsApp Bot Integration

Add a new command for CV generation:

```python
# In your WhatsApp handler
if message.lower() == "generate cv":
    # Collect CV data through conversation
    job = create_job(user, job_type="cv")
    cv_bytes = render_cv(job)
    send_document(user, cv_bytes, "cv.docx")
```

### Option 3: API Endpoint

```python
from flask import send_file
from io import BytesIO

@app.route('/api/cv/<job_id>')
def download_cv(job_id):
    job = Job.query.get(job_id)
    cv_bytes = render_cv(job)
    
    return send_file(
        BytesIO(cv_bytes),
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        as_attachment=True,
        download_name=f'cv_{job.id}.docx'
    )
```

---

## 📝 Minimum Required Data

Only these fields are absolutely required:

```python
minimum_cv_data = {
    "basics": {
        "name": "Your Name",    # Required
        "title": "Your Title",  # Required
        "email": "your@email"   # Recommended
    },
    "summary": "Brief description...",  # Recommended
    "experiences": [                     # At least one recommended
        {
            "company": "Company",
            "role": "Role",
            "start": "Jan 2020",
            "end": "Present"
        }
    ]
}
```

All other sections are optional.

---

## 🎨 Customization

### Change Section Order

Sections are rendered in this order:
1. Header (name, title, contact)
2. Profiles
3. Summary
4. Experience
5. Education
6. References
7. Skills

To change order, modify `backend/app/services/renderer.py` in the `render_cv()` function.

### Adjust Spacing

```python
# In renderer.py, modify these values:

# Page margins
section.top_margin = Inches(0.5)    # Decrease for more space
section.bottom_margin = Inches(0.5)
section.left_margin = Inches(0.7)
section.right_margin = Inches(0.7)

# Section spacing
heading.paragraph_format.space_before = Pt(6)  # Change these
heading.paragraph_format.space_after = Pt(4)
```

### Change Font Sizes

```python
# Name size
name_run.font.size = Pt(20)  # Make bigger/smaller

# Section headers
heading_run.font.size = Pt(11)

# Body text
run.font.size = Pt(10)
```

---

## 🔍 Data Validation

Before generating, validate your data:

```python
def validate_cv_data(data):
    """Quick validation check"""
    errors = []
    
    # Check basics
    if not data.get("basics", {}).get("name"):
        errors.append("Name is required")
    
    if not data.get("basics", {}).get("title"):
        errors.append("Title is required")
    
    # Check experiences
    experiences = data.get("experiences", [])
    for i, exp in enumerate(experiences):
        if not exp.get("company"):
            errors.append(f"Experience {i+1}: Company is required")
        if not exp.get("role"):
            errors.append(f"Experience {i+1}: Role is required")
    
    return errors

# Usage
errors = validate_cv_data(cv_data)
if errors:
    print("Validation errors:", errors)
else:
    cv_bytes = render_cv(job)
```

---

## 🐛 Troubleshooting

### Issue: Generated CV is too long (multiple pages)

**Solution:** Reduce content or spacing:
- Shorten summary paragraph
- Use fewer bullet points (1-2 per role)
- Reduce number of skills
- Decrease margins slightly

### Issue: Dates not right-aligned

**Solution:** Check tab stop position:
```python
# Should be 6.0 inches
tab_stops.add_tab_stop(Inches(6.0), WD_TAB_ALIGNMENT.RIGHT)
```

### Issue: Skills not in two columns

**Solution:** Verify skills table code runs without errors. Check that skills list has items.

### Issue: Icons not showing (□ boxes instead)

**Solution:** Unicode icons should work. If not, replace with regular text:
```python
# Instead of
contact_parts.append(f"📍 {location}")

# Use
contact_parts.append(f"Location: {location}")
```

---

## 📚 Reference Documents

For detailed information, see:

1. **CV_TEMPLATE_DOCUMENTATION.md** - Complete specifications
2. **CV_LAYOUT_VISUAL_REFERENCE.md** - Visual layout guide
3. **CV_TEMPLATE_IMPLEMENTATION_SUMMARY.md** - Implementation details
4. **test_cv_generation.py** - Working example with sample data

---

## ✅ Pre-Flight Checklist

Before deploying to production:

- [ ] Test with minimum data
- [ ] Test with maximum data (long text)
- [ ] Test with missing optional fields
- [ ] Verify right-alignment works
- [ ] Check output is single page
- [ ] Test on different devices/systems
- [ ] Verify DOCX opens in Word/Google Docs
- [ ] Check all sections render correctly
- [ ] Validate data before rendering
- [ ] Add error handling

---

## 💡 Pro Tips

### Tip 1: Reuse Existing Data
If you already collect resume data, reuse it for CVs:
```python
# Resume data can be transformed to CV data
cv_data = transform_resume_to_cv(resume_data)
```

### Tip 2: Provide Templates
Offer users example CVs for different roles:
- Teaching CV template
- Academic CV template
- Administrative CV template

### Tip 3: Auto-Format Dates
```python
# Convert various date formats to "MMM YYYY"
from datetime import datetime

def format_date(date_str):
    """Convert to MMM YYYY format"""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%b %Y")  # "Jan 2020"
    except:
        return date_str  # Return as-is if parsing fails
```

### Tip 4: Suggest Skills
Based on job title, suggest relevant skills:
```python
SKILL_SUGGESTIONS = {
    "Teacher": ["Classroom Management", "Curriculum Design", "Student Assessment"],
    "Manager": ["Leadership", "Project Management", "Team Building"],
    # Add more...
}

def suggest_skills(job_title):
    return SKILL_SUGGESTIONS.get(job_title, [])
```

---

## 🚀 Next Steps

1. ✅ **Test** - Run `python test_cv_generation.py`
2. ✅ **Review** - Open `backend/output/test_cv_sample.docx`
3. ✅ **Integrate** - Add to your existing workflow
4. ✅ **Deploy** - Make available to users
5. ✅ **Monitor** - Track usage and feedback

---

## 📞 Need Help?

- **Documentation:** See `CV_TEMPLATE_DOCUMENTATION.md`
- **Visual Guide:** See `CV_LAYOUT_VISUAL_REFERENCE.md`
- **Sample Code:** See `backend/test_cv_generation.py`
- **Implementation:** See `CV_TEMPLATE_IMPLEMENTATION_SUMMARY.md`

---

**Quick Reference:**

| File | Purpose |
|------|---------|
| `backend/app/services/renderer.py` | Main CV generator |
| `backend/test_cv_generation.py` | Test script |
| `backend/output/test_cv_sample.docx` | Sample output |

**Status:** ✅ Ready to use immediately

**Last Updated:** January 2, 2026



