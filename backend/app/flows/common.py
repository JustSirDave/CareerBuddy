from typing import Dict, Tuple

STEP_ORDER = [
    "basics",         # name, title, contacts
    "summary",
    "skills",
    "experience",     # repeatable
    "education",
    "extras"          # projects/certs/links
]

def next_step(current: str | None) -> str | None:
    if current is None:
        return STEP_ORDER[0]
    try:
        idx = STEP_ORDER.index(current)
        return STEP_ORDER[idx + 1] if idx + 1 < len(STEP_ORDER) else None
    except ValueError:
        return STEP_ORDER[0]

def specificity_probe(section: str, payload: Dict) -> list[str]:
    # super-light probe using rules/specificity.json (static import)
    # You can expand this later.
    missing = []
    if section == "experience":
        bullet_has_number = any(ch.isdigit() for b in payload.get("bullets", []) for ch in b)
        if not bullet_has_number:
            missing.append("Add one metric (%, count, or time).")
    return missing

def normalize_yesno(text: str) -> bool | None:
    t = (text or "").strip().lower()
    if t in {"y","yes","yeah","sure"}: return True
    if t in {"n","no","nope"}: return False
    return None
