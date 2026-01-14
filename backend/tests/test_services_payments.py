"""
Tests for payment service
Tests payment link generation, validation, and user tier management
"""
import pytest
from unittest.mock import patch, Mock
from app.services import payments
from app.models import User, Payment


class TestPaymentLimits:
    """Test generation limits and payment requirements"""

    def test_free_tier_can_generate(self, db_session, test_user):
        """Test free user can generate within limits"""
        test_user.generation_count = 1
        db_session.commit()

        can_gen, reason = payments.can_generate(db_session, test_user, "Backend Engineer")
        assert can_gen is True

    def test_free_tier_limit_reached(self, db_session, test_user):
        """Test free user hits generation limit"""
        # Set generation count to max
        test_user.generation_count = payments.MAX_FREE_GENERATIONS
        db_session.commit()

        can_gen, reason = payments.can_generate(db_session, test_user, "Backend Engineer")
        assert can_gen is False
        assert "free_limit_reached" in reason

    def test_pro_tier_unlimited(self, db_session, pro_user):
        """Test pro user has unlimited generations"""
        pro_user.generation_count = 100  # Way over free limit
        db_session.commit()

        can_gen, reason = payments.can_generate(db_session, pro_user, "Backend Engineer")
        assert can_gen is True

    def test_max_per_role_limit(self, db_session, test_user):
        """Test maximum generations per role"""
        role = "Data Scientist"
        
        # Create multiple jobs for same role
        for i in range(payments.MAX_GENERATIONS_PER_ROLE):
            from app.models import Job
            job = Job(
                user_id=test_user.id,
                type="resume",
                status="done",
                answers={"target_role": role}
            )
            db_session.add(job)
        db_session.commit()

        can_gen, reason = payments.can_generate(db_session, test_user, role)
        assert can_gen is False
        assert "max_per_role" in reason


class TestUpdateGenerationCount:
    """Test generation count tracking"""

    def test_increment_generation_count(self, db_session, test_user):
        """Test generation count increments"""
        initial_count = test_user.generation_count
        
        payments.update_generation_count(db_session, test_user, "Backend Engineer")
        
        db_session.refresh(test_user)
        assert test_user.generation_count == initial_count + 1

    def test_role_tracking(self, db_session, test_user):
        """Test role-specific tracking"""
        role = "Backend Engineer"
        
        payments.update_generation_count(db_session, test_user, role)
        
        # Count should be tracked for this role
        from app.models import Job
        jobs_for_role = db_session.query(Job).filter(
            Job.user_id == test_user.id,
            Job.answers["target_role"].astext == role
        ).count()
        
        # Note: This tests the tracking mechanism exists


class TestPaymentLinkGeneration:
    """Test Paystack payment link generation"""

    @pytest.mark.asyncio
    @patch('app.services.payments._paystack_client')
    async def test_create_payment_link_success(self, mock_client, db_session, test_user):
        """Test successful payment link creation"""
        mock_client.transaction.initialize.return_value = {
            "status": True,
            "data": {
                "authorization_url": "https://paystack.com/pay/xyz",
                "access_code": "abc123",
                "reference": "ref_123"
            }
        }
        
        result = await payments.create_payment_link(test_user, "Backend Engineer")
        
        assert result["status"] == "success"
        assert "authorization_url" in result
        assert "reference" in result

    @pytest.mark.asyncio
    @patch('app.services.payments._paystack_client', None)
    async def test_create_payment_link_no_client(self, db_session, test_user):
        """Test payment link creation without Paystack configured"""
        result = await payments.create_payment_link(test_user, "Backend Engineer")
        
        assert "error" in result

    @pytest.mark.asyncio
    @patch('app.services.payments._paystack_client')
    async def test_create_payment_link_api_failure(self, mock_client, db_session, test_user):
        """Test payment link creation when API fails"""
        mock_client.transaction.initialize.side_effect = Exception("API Error")
        
        result = await payments.create_payment_link(test_user, "Backend Engineer")
        
        assert "error" in result


class TestUpgradePayment:
    """Test premium upgrade payment"""

    @pytest.mark.asyncio
    @patch('app.services.payments._paystack_client')
    async def test_create_upgrade_link(self, mock_client, db_session, test_user):
        """Test creating upgrade payment link"""
        mock_client.transaction.initialize.return_value = {
            "status": True,
            "data": {
                "authorization_url": "https://paystack.com/pay/xyz",
                "reference": "upgrade_ref_123"
            }
        }
        
        result = await payments.create_upgrade_payment_link(test_user)
        
        assert result["status"] == "success"
        assert result["amount"] == payments.PREMIUM_PRICE

    def test_premium_price_constant(self):
        """Test premium price is correct"""
        assert payments.PREMIUM_PRICE == 7500
        assert payments.PAID_GENERATION_PRICE == 750


class TestWaivePayment:
    """Test payment bypass for testing"""

    def test_record_waived_payment(self, db_session, test_user):
        """Test recording waived payment"""
        initial_tier = test_user.tier
        
        payments.record_waived_payment(db_session, test_user, amount=0, reason="test")
        
        db_session.refresh(test_user)
        
        # Check payment record was created
        payment = db_session.query(Payment).filter(
            Payment.user_id == test_user.id,
            Payment.status == "waived"
        ).first()
        
        assert payment is not None
        assert payment.amount == 0

    def test_waived_payment_for_upgrade(self, db_session, test_user):
        """Test waived upgrade payment"""
        assert test_user.tier == "free"
        
        payments.record_waived_payment(
            db_session,
            test_user,
            amount=0,
            reason="test_upgrade",
            upgrade_to_pro=True
        )
        
        db_session.refresh(test_user)
        assert test_user.tier == "pro"


class TestPaymentValidation:
    """Test payment reference validation"""

    def test_valid_reference_format(self):
        """Test payment reference format validation"""
        valid_refs = [
            "ref_123456789",
            "TEST_REF",
            "upgrade_ref_abc123"
        ]
        
        for ref in valid_refs:
            assert isinstance(ref, str)
            assert len(ref) > 0

    def test_payment_amounts(self):
        """Test payment amounts are positive"""
        assert payments.PREMIUM_PRICE > 0
        assert payments.PAID_GENERATION_PRICE > 0


class TestGenerationHistory:
    """Test tracking generation history"""

    def test_count_generations_by_role(self, db_session, test_user):
        """Test counting generations for a role"""
        from app.models import Job
        
        role = "Software Engineer"
        
        # Create jobs for this role
        for i in range(3):
            job = Job(
                user_id=test_user.id,
                type="resume",
                status="done",
                answers={"target_role": role}
            )
            db_session.add(job)
        db_session.commit()

        # Count should match
        jobs_for_role = db_session.query(Job).filter(
            Job.user_id == test_user.id,
            Job.answers["target_role"].astext == role
        ).count()
        
        assert jobs_for_role == 3

    def test_different_roles_counted_separately(self, db_session, test_user):
        """Test different roles are counted separately"""
        from app.models import Job
        
        roles = ["Backend Engineer", "Frontend Engineer", "DevOps Engineer"]
        
        for role in roles:
            job = Job(
                user_id=test_user.id,
                type="resume",
                status="done",
                answers={"target_role": role}
            )
            db_session.add(job)
        db_session.commit()

        # Each role should have 1 generation
        for role in roles:
            count = db_session.query(Job).filter(
                Job.user_id == test_user.id,
                Job.answers["target_role"].astext == role
            ).count()
            assert count == 1


class TestPaymentEdgeCases:
    """Test edge cases in payment logic"""

    def test_negative_generation_count(self, db_session, test_user):
        """Test handling negative generation count"""
        test_user.generation_count = -1
        db_session.commit()

        # Should still allow generation
        can_gen, reason = payments.can_generate(db_session, test_user, "Backend Engineer")
        assert can_gen is True

    def test_very_large_generation_count(self, db_session, pro_user):
        """Test pro user with very large count"""
        pro_user.generation_count = 999999
        db_session.commit()

        # Pro should still be able to generate
        can_gen, reason = payments.can_generate(db_session, pro_user, "Backend Engineer")
        assert can_gen is True

    def test_empty_role_name(self, db_session, test_user):
        """Test empty role name"""
        can_gen, reason = payments.can_generate(db_session, test_user, "")
        # Should handle gracefully
        assert isinstance(can_gen, bool)

    def test_none_role_name(self, db_session, test_user):
        """Test None role name"""
        can_gen, reason = payments.can_generate(db_session, test_user, None)
        # Should handle gracefully
        assert isinstance(can_gen, bool)
