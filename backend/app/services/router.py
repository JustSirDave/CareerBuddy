from __future__ import annotations
from loguru import logger
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models import User, Job, Message
from app.flows import resume as resume_flow
from app.services.idempotency import seen_or_mark

WELCOME = "Hi! What would you like to create first?\nReply with *Resume*, *CV*, or *Cover Letter*."
GREETINGS = {"hi", "hello", "hey", "start", "menu"}
RESETS = {"reset", "/reset", "restart"}
FORCE_LOWER = lambda s: (s or "").strip().lower()


def _advance(db: Session, job: Job, answers: dict, next_step: str):
    """
    Advance to the next step AND commit immediately to prevent loops.
    """
    answers["_step"] = next_step
    job.answers = answers
    # CRITICAL: Tell SQLAlchemy the JSON field was modified
    flag_modified(job, "answers")
    db.commit()
    db.refresh(job)
    logger.info(f"[_advance] job.id={job.id} advanced to step={next_step}")


def _dedupe(db: Session, job: Job, msg_id: str | None) -> bool:
    """
    Return True if this is a duplicate and should be ignored.
    Commit immediately to prevent race conditions.
    """
    if not msg_id:
        return False
    if job.last_msg_id == msg_id:
        logger.warning(f"[dedupe] Duplicate msg_id={msg_id}, ignoring.")
        return True

    job.last_msg_id = msg_id
    db.commit()
    logger.info(f"[dedupe] Marked msg_id={msg_id} as seen")
    return False


def _log_state(when: str, job: Job | None):
    if not job:
        logger.info(f"[router] {when}: job=None")
        return
    ans = job.answers if isinstance(job.answers, dict) else {}
    logger.info(
        f"[router] {when}: job.id={job.id} type={job.type} status={job.status} "
        f"keys={list(ans.keys())} step={ans.get('_step')}"
    )


def infer_type(text: str) -> str | None:
    t = (text or "").strip().lower()
    if t == "choose_resume":
        return "resume"
    if t == "choose_cv":
        return "cv"
    if t == "choose_cover":
        return "cover"
    if "resume" in t:
        return "resume"
    if t == "cv" or " cv " in f" {t} ":
        return "cv"
    if "cover" in t:
        return "cover"
    return None


def _active_collecting_job(db: Session, user_id):
    return (
        db.query(Job)
        .filter(Job.user_id == user_id, Job.status == "collecting")
        .order_by(Job.created_at.desc())
        .first()
    )


def _new_job(db: Session, user_id, doc_type: str) -> Job:
    job = Job(
        user_id=user_id,
        type=doc_type,
        status="collecting",
        answers=resume_flow.start_context() | {"_step": "basics"},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    logger.info(f"[new_job] Created job.id={job.id} type={doc_type}")
    return job


def get_active_job(db: Session, user_id, doc_type: str | None) -> Job | None:
    if doc_type:
        existing = (
            db.query(Job)
            .filter(Job.user_id == user_id, Job.status == "collecting", Job.type == doc_type)
            .order_by(Job.created_at.desc())
            .first()
        )
        return existing or _new_job(db, user_id, doc_type)
    return _active_collecting_job(db, user_id)


def maybe_finalize(db: Session, job: Job) -> bool:
    ans = job.answers if isinstance(job.answers, dict) else {}
    basics_ok = bool(ans.get("basics", {}).get("name"))
    has_exp = len(ans.get("experiences", [])) >= 1
    last_has_bullets = has_exp and len(ans["experiences"][-1].get("bullets", [])) >= 1
    
    if basics_ok and last_has_bullets:
        job.status = "draft_ready"
        db.commit()
        logger.info(f"[finalize] job.id={job.id} → draft_ready")
        return True
    return False


def handle_resume(db: Session, job: Job, text: str) -> str:
    answers = job.answers or resume_flow.start_context()
    step = FORCE_LOWER(answers.get("_step") or "basics")
    t = (text or "").strip()
    logger.info(f"[resume] step={step} text='{t[:80]}'")

    # ---- BASICS ----
    if step == "basics":
        if answers.get("basics", {}).get("name"):
            _advance(db, job, answers, "summary")
            return resume_flow.QUESTIONS["summary"]
        if "," not in t:
            return resume_flow.QUESTIONS["basics"]

        answers["basics"] = resume_flow.parse_basics(t)
        _advance(db, job, answers, "summary")
        return resume_flow.QUESTIONS["summary"]

    # ---- SUMMARY ----
    if step == "summary":
        if not t or t.lower() == "skip":
            answers["summary"] = resume_flow.draft_summary(answers)
        else:
            answers["summary"] = t
        _advance(db, job, answers, "skills")
        return resume_flow.QUESTIONS["skills"]

    # ---- SKILLS ----
    if step == "skills":
        if not t or t.lower() == "skip":
            answers["skills"] = answers.get("skills", [])
        else:
            answers["skills"] = resume_flow.parse_skills(t)
        _advance(db, job, answers, "experience_header")
        return resume_flow.QUESTIONS["experience"]

    # ---- EXPERIENCE HEADER ----
    if step == "experience_header":
        if t.lower() == "skip":
            _advance(db, job, answers, "education")
            return resume_flow.QUESTIONS["education"]
        
        header = resume_flow.parse_experience_header(t)
        if not header.get("role"):
            return ("Please send: Role, Company, City, Start (MMM YYYY), "
                    "End (MMM YYYY or Present)")
        
        exps = list(answers.get("experiences", []))
        exps.append(header)
        answers["experiences"] = exps
        _advance(db, job, answers, "experience_bullets")
        return "Great. Now send 2–4 bullet points (one per message). Type *done* when finished."

    # ---- EXPERIENCE BULLETS ----
    if step == "experience_bullets":
        lt = t.lower()
        exps = list(answers.get("experiences", []))
        if not exps:
            _advance(db, job, answers, "experience_header")
            return resume_flow.QUESTIONS["experience"]

        if lt == "done" or lt == "skip":
            _advance(db, job, answers, "add_another_experience")
            return "Add another experience? (Reply: yes / no)"

        if t:
            exps[-1]["bullets"].append(t.strip())
            answers["experiences"] = exps
            job.answers = answers
            flag_modified(job, "answers")
            db.commit()
        
        return "Add another bullet or type *done*."

    # ---- ADD ANOTHER EXPERIENCE ----
    if step == "add_another_experience":
        lt = t.lower()
        if lt in {"yes", "y", "add", "add another"}:
            _advance(db, job, answers, "experience_header")
            return resume_flow.QUESTIONS["experience"]
        
        _advance(db, job, answers, "education")
        return resume_flow.QUESTIONS["education"]

    # ---- EDUCATION ----
    if step == "education":
        if not t or t.lower() == "skip":
            _advance(db, job, answers, "extras")
            return resume_flow.QUESTIONS["extras"]
        
        edus = list(answers.get("education", []))
        edus.append({"details": t})
        answers["education"] = edus
        job.answers = answers
        flag_modified(job, "answers")
        db.commit()
        return "Added. Send another or *skip*."

    # ---- EXTRAS ----
    if step == "extras":
        lt = t.lower()
        if not t or lt in {"done", "skip"}:
            _advance(db, job, answers, "finalize")
            return "All set. Finalizing your draft…"
        
        projs = list(answers.get("projects", []))
        projs.append({"details": t})
        answers["projects"] = projs
        job.answers = answers
        flag_modified(job, "answers")
        db.commit()
        return "Got it. Add more or type *done*."

    # ---- FINALIZE ----
    if step == "finalize":
        job.status = "draft_ready"
        _advance(db, job, answers, "done")
        return "Draft ready. I'll render a preview next. Reply /reset to start another."

    # Safety: never fall back; re-ask current step
    return resume_flow.QUESTIONS.get(step, resume_flow.QUESTIONS["basics"])


def handle_inbound(db: Session, wa_id: str, text: str, msg_id: str | None = None) -> str:
    # Drop duplicates at the global level (before user/job lookup)
    if msg_id and seen_or_mark(msg_id):
        logger.warning(f"[handle_inbound] Global duplicate msg_id={msg_id}, ignoring.")
        return ""
    
    # 0) Ensure user
    user = db.query(User).filter(User.wa_id == wa_id).first()
    if not user:
        user = User(wa_id=wa_id)
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"[handle_inbound] Created new user wa_id={wa_id}")

    incoming = (text or "").strip()
    t_lower = incoming.lower()

    # 1) Log inbound message
    db.add(Message(user_id=user.id, direction="inbound", content=incoming))
    db.commit()

    # 2) Reset/menu
    if t_lower in RESETS:
        j = _active_collecting_job(db, user.id)
        if j:
            j.status = "closed"
            db.commit()
            logger.info(f"[handle_inbound] Reset triggered, closed job.id={j.id}")
        return "__SHOW_MENU__"

    if t_lower in GREETINGS:
        return "__SHOW_MENU__"

    # 3) Get/create active job (based on intent if present)
    doc_type = infer_type(incoming)
    job = get_active_job(db, user.id, doc_type)
    _log_state("after get_active_job", job)

    if not job and not doc_type:
        return "__SHOW_MENU__"

    # 4) Job-level deduplication (prevent double-processing same message)
    if _dedupe(db, job, msg_id):
        return ""  # Already processed

    # 5) Ensure answers dict + step
    ans = job.answers if isinstance(job.answers, dict) else {}
    if not ans or not ans.get("_step"):
        ans = resume_flow.start_context()
        ans["_step"] = "basics"
        job.answers = ans
        flag_modified(job, "answers")
        db.commit()
        logger.info(f"[handle_inbound] Initialized job.id={job.id} with step=basics")

    logger.info(f"[router] before step-check, step={ans.get('_step')}")

    # 6) Route to the correct flow
    if job.type in {"resume", "cv"}:
        reply = handle_resume(db, job, incoming)
        _log_state("after handle_resume", job)
    else:
        reply = "Cover letter flow is coming next. For now, reply *Resume* or *CV* to begin."

    # 7) Optional finalize hook
    if maybe_finalize(db, job):
        reply += "\n\n✅ Draft ready! (status = draft_ready)"

    # 8) Log outbound message
    db.add(Message(user_id=user.id, job_id=job.id, direction="outbound", content=reply or ""))
    db.commit()
    
    return reply