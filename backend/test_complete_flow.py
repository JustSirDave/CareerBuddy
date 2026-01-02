"""
Quick test script to verify the complete resume flow with AI integration.
Run this from the backend directory: python test_complete_flow.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import User, Job
from app.services.router import handle_inbound
from app.config import settings
from loguru import logger

# Setup
logger.info("Setting up test database connection...")
engine = create_engine(settings.database_url)
Session = sessionmaker(bind=engine)

def test_complete_flow():
    """Simulate complete resume creation flow."""
    db = Session()

    # Test user WhatsApp ID
    wa_id = "TEST_USER_12345@c.us"

    print("\n" + "="*80)
    print("🧪 TESTING COMPLETE RESUME FLOW WITH AI")
    print("="*80 + "\n")

    # Clean up any existing test data
    db.query(Job).filter(Job.user_id.in_(
        db.query(User.id).filter(User.wa_id == wa_id)
    )).delete(synchronize_session=False)
    db.query(User).filter(User.wa_id == wa_id).delete()
    db.commit()

    steps = [
        ("1️⃣  Start", "Resume"),
        ("2️⃣  Basics", "David Lucas, david@example.com, +234-123-4567, Lagos Nigeria"),
        ("3️⃣  Target Role", "Senior Backend Engineer"),
        ("4️⃣  Experience Header", "Backend Engineer, TechCorp, Lagos, Jan 2020, Present"),
        ("5️⃣  Experience Bullet 1", "Built scalable REST APIs serving 1M+ daily requests"),
        ("6️⃣  Experience Bullet 2", "Reduced database query time by 60% through optimization"),
        ("7️⃣  Experience Bullet 3", "Led migration to microservices architecture"),
        ("8️⃣  Done with bullets", "done"),
        ("9️⃣  Add another experience?", "no"),
        ("🔟 Education", "B.Sc. Computer Science, University of Lagos, 2020"),
        ("1️⃣1️⃣ Skip more education", "skip"),
        ("1️⃣2️⃣ Extras", "AWS Certified Solutions Architect"),
        ("1️⃣3️⃣ Done with extras", "done"),
        ("1️⃣4️⃣ AI Skills - Select", "1,2,3,4,5"),  # Select first 5 skills
        ("1️⃣5️⃣ AI Summary - Approve", "yes"),  # Approve AI summary
        ("1️⃣6️⃣ Preview - Confirm", "yes"),  # Confirm preview
    ]

    try:
        for i, (step_name, message) in enumerate(steps, 1):
            print(f"\n{step_name}: '{message}'")
            print("-" * 80)

            response = handle_inbound(db, wa_id, message, f"test_msg_{i}")

            # Print bot response (truncated for readability)
            if response:
                lines = response.split('\n')
                if len(lines) > 10:
                    print('\n'.join(lines[:10]))
                    print(f"... ({len(lines) - 10} more lines)")
                else:
                    print(response)

            # Check for errors
            if "error" in response.lower() or "failed" in response.lower():
                print(f"\n❌ ERROR detected in response!")
                return False

            # Special checks for AI steps
            if i == 14:  # AI Skills step
                if "🤖" in response or any(str(j) in response for j in range(1, 11)):
                    print("✅ AI skills generated successfully!")
                else:
                    print("⚠️  AI skills may not have generated")

            if i == 15:  # AI Summary step
                if "🤖" in response or "Generated Summary" in response:
                    print("✅ AI summary generated successfully!")
                else:
                    print("⚠️  AI summary may not have generated")

            if i == 16:  # Preview step
                if "Preview" in response or "Draft" in response or "📋" in response:
                    print("✅ Preview displayed!")
                else:
                    print("⚠️  Preview may not have displayed")

        # Check final job status
        user = db.query(User).filter(User.wa_id == wa_id).first()
        if user:
            jobs = db.query(Job).filter(Job.user_id == user.id).all()
            print(f"\n\n📊 FINAL STATUS:")
            print("-" * 80)
            for job in jobs:
                print(f"Job ID: {job.id}")
                print(f"Status: {job.status}")
                print(f"Type: {job.type}")

                answers = job.answers or {}
                print(f"\nCollected Data:")
                print(f"  - Name: {answers.get('basics', {}).get('name', 'N/A')}")
                print(f"  - Target Role: {answers.get('target_role', 'N/A')}")
                print(f"  - Skills: {answers.get('skills', [])}")
                print(f"  - Summary: {answers.get('summary', 'N/A')[:100]}...")
                print(f"  - Experiences: {len(answers.get('experiences', []))} entries")
                print(f"  - Education: {len(answers.get('education', []))} entries")
                print(f"  - Step: {answers.get('_step', 'N/A')}")

                # Verify AI data
                has_skills = len(answers.get('skills', [])) > 0
                has_summary = len(answers.get('summary', '')) > 10

                print(f"\n✅ AI Skills populated: {has_skills}")
                print(f"✅ AI Summary populated: {has_summary}")

                if job.status == "done" and has_skills and has_summary:
                    print("\n" + "="*80)
                    print("🎉 TEST PASSED! Complete flow works with AI integration!")
                    print("="*80)
                    return True
                elif job.status == "draft_ready":
                    print("\n⚠️  Job marked as draft_ready (may need to finalize)")
                elif job.status == "collecting":
                    print("\n⚠️  Job still collecting (flow not complete)")

        print("\n" + "="*80)
        print("❌ TEST INCOMPLETE: Flow did not reach 'done' status or missing AI data")
        print("="*80)
        return False

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    print("\n🚀 Starting CareerBuddy Complete Flow Test...")
    print(f"🔑 OpenAI API Key: {'✅ SET' if settings.openai_api_key else '❌ NOT SET'}\n")

    if not settings.openai_api_key:
        print("⚠️  WARNING: OpenAI API key not set - AI features will use fallback!\n")

    success = test_complete_flow()
    sys.exit(0 if success else 1)
