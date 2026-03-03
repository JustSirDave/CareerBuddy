"""
Onboarding flow for new CareerBuddy users.
Handles warm welcome -> intent detection -> flow transition.
Author: Sir Dave
"""
from sqlalchemy.orm import Session

from app.models import User, Job
from app.flows import resume as resume_flow
from app.services import ai, payments


ONBOARDING_WELCOME = """Hey {first_name} 👋 Welcome to CareerBuddy!

I'm your personal career document assistant. I help you create professional, ATS-optimized resumes, CVs, and cover letters — through a simple conversation, in minutes.

Before we dive in — what brings you here today? Tell me a little about what you're looking for.

_(e.g. "I need a new resume", "I'm applying for a job at GTBank", "I want to update my CV")_"""

RETURNING_USER_MENU = """Welcome back, {first_name}! 👋

Good to see you again. Ready to create another document?
What do you need today?"""

ACTIVE_JOB_PROMPT = """Hey {first_name}, you've got a {doc_type} in progress!

Want to continue where you left off, or start something new?"""

SOFT_MENU_PROMPT = """Got it! Let me show you what I can help you with:"""

BUNDLE_PROMPT = """I can help you with several document types. Which would you like to start with?"""


def handle_new_user_welcome(db: Session, user: User, first_name: str) -> str:
    user.onboarding_step = "awaiting_intent_response"
    user.onboarding_complete = False
    db.commit()
    db.refresh(user)
    return ONBOARDING_WELCOME.format(first_name=first_name)


def handle_onboarding_intent_response(
    db: Session, user: User, message_text: str, telegram_user_id: str, first_name: str
) -> str:
    result = ai.detect_onboarding_intent(message_text)
    intent = result.get("intent", "unclear")
    confidence = result.get("confidence", "low")
    extracted_role = result.get("extracted_role")
    extracted_company = result.get("extracted_company")

    if intent == "cover_letter" and not payments.can_generate(user, "cover"):
        user.onboarding_complete = True
        user.onboarding_step = None
        db.commit()
        msg = (
            "You've used your free cover letter credit.\n\n"
            "You can purchase more with /buy\\_cover\\_letter, "
            "or I can help you with a Resume or CV instead."
        )
        return f"__SHOW_DOCUMENT_MENU__|credits|{msg}"

    if confidence == "high" and intent in ("resume", "cv", "cover_letter"):
        return _transition_to_flow(db, user, intent, extracted_role, extracted_company, first_name)

    if intent == "bundle":
        user.onboarding_complete = True
        user.onboarding_step = None
        db.commit()
        return f"__SHOW_DOCUMENT_MENU__|credits|{BUNDLE_PROMPT}"

    user.onboarding_complete = True
    user.onboarding_step = None
    db.commit()
    return f"__SHOW_DOCUMENT_MENU__|credits|{SOFT_MENU_PROMPT}"


def _transition_to_flow(
    db: Session, user: User, intent: str, extracted_role: str | None,
    extracted_company: str | None, first_name: str
) -> str:
    user.onboarding_complete = True
    user.onboarding_step = None
    db.commit()
    db.refresh(user)

    job_type = "cover" if intent == "cover_letter" else intent

    if not payments.can_generate(user, job_type):
        return payments.get_purchase_prompt(job_type)

    answers = resume_flow.start_context() | {"_step": "basics"}
    if extracted_role:
        answers["target_role"] = extracted_role
    if extracted_company and intent == "cover_letter":
        answers["cover_company"] = extracted_company

    job = Job(user_id=user.id, type=job_type, status="collecting", answers=answers)
    db.add(job)
    db.commit()
    db.refresh(job)

    doc_label = {"resume": "resume", "cv": "CV", "cover_letter": "cover letter"}.get(intent, intent)
    transition_msg = f"Great! Let's build your {doc_label}. I'll guide you step by step.\n\n"
    return transition_msg + resume_flow.QUESTIONS["basics"]
