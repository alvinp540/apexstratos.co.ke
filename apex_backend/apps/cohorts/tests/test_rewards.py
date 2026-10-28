from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.urls import reverse
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.cohorts.models import (
    SponsoredViewAssessment,
    SponsoredViewAttempt,
    SponsoredViewDailySettlement,
    SponsoredViewPayment,
    SponsoredViewAttempt,
    SponsoredViewQuestion,
    SponsoredViewSettlementAdjustment,
    SupportProgram,
)
from apps.cohorts.reward_settlement import settle_sponsored_view_assessment
from apps.notifications.models import Notification
from apps.cohorts.payouts import PayoutProviderNotConfigured, get_reward_payout_provider


EAT = ZoneInfo('Africa/Nairobi')
SETTLEMENT_DAY = datetime(2026, 10, 12, tzinfo=EAT).date()


class SponsoredRewardSettlementTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email='rewards-admin@example.test', username='rewards-admin',
            password='test-password', role='admin', is_staff=True,
        )
        self.assessment = SponsoredViewAssessment.objects.create(
            week=1, slot=8, field='Software Development', title='Daily reward test',
            description='Assessment used to test daily reward settlement.',
            learning_objectives=['A', 'B', 'C'], status='published',
        )
        for order in range(1, 11):
            SponsoredViewQuestion.objects.create(
                assessment=self.assessment, order=order, prompt=f'Question {order}',
                options=['A', 'B'], correct_answer='A', rationale='Test rationale',
            )

    def add_participant(self, index, score, *, verified=True, flagged=False):
        user = User.objects.create_user(
            email=f'reward-student-{index}@example.test',
            username=f'reward-student-{index}', password='test-password',
            phone_number=f'071234{index:04d}',
        )
        payment = SponsoredViewPayment.objects.create(
            user=user, assessment=self.assessment, amount_kes=20,
            payment_reference=f'REWARD-PAY-{index}',
            mpesa_transaction_id=f'REWARD-TXN-{index}' if verified else '',
            status='verified' if verified else 'pending',
            verified_at=datetime(2026, 10, 12, 10, tzinfo=EAT) if verified else None,
        )
        SponsoredViewAttempt.objects.create(
            payment=payment, user=user, assessment=self.assessment,
            question_snapshot=[], answers={}, score=score, status='graded',
            started_at=datetime(2026, 10, 12, 9, tzinfo=EAT),
            deadline_at=datetime(2026, 10, 12, 10, tzinfo=EAT),
            submitted_at=datetime(2026, 10, 12, 10, tzinfo=EAT),
            is_flagged=flagged,
        )
        return user, payment

    def test_fifty_eligible_payments_allocate_half_to_platform_and_five_awards(self):
        for index in range(50):
            self.add_participant(index, 95)
        settlement, created = settle_sponsored_view_assessment(self.assessment.id, SETTLEMENT_DAY)
        self.assertTrue(created)
        self.assertEqual(settlement.eligible_participant_count, 50)
        self.assertEqual(settlement.total_revenue_kes, 1000)
        self.assertEqual(settlement.platform_share_kes, 500)
        self.assertEqual(settlement.rewards_budget_kes, 500)
        self.assertEqual(settlement.awarded_total_kes, 500)
        self.assertEqual(settlement.awards.count(), 5)
        self.assertEqual(settlement.unallocated_reserve_kes, 0)

    def test_one_hundred_participants_fund_ten_standard_awards(self):
        for index in range(100):
            self.add_participant(index, 95)
        settlement, _ = settle_sponsored_view_assessment(self.assessment.id, SETTLEMENT_DAY)
        self.assertEqual(settlement.total_revenue_kes, 2000)
        self.assertEqual(settlement.platform_share_kes, 1000)
        self.assertEqual(settlement.rewards_budget_kes, 1000)
        self.assertEqual(settlement.awards.count(), 10)

    def test_finalized_timed_out_attempt_remains_eligible_for_daily_reward_settlement(self):
        timed_out_user, _payment = self.add_participant(500, 95)
        attempt = SponsoredViewAttempt.objects.get(user=timed_out_user)
        attempt.status = 'timed_out'
        attempt.save(update_fields=('status',))
        for index in range(501, 510):
            self.add_participant(index, 80)

        settlement, _created = settle_sponsored_view_assessment(self.assessment.id, SETTLEMENT_DAY)

        self.assertEqual(settlement.eligible_participant_count, 10)
        self.assertEqual(settlement.total_revenue_kes, 200)
        self.assertEqual(settlement.awards.filter(user=timed_out_user).count(), 1)

    def test_secondary_ranking_fills_awards_and_idempotent_retry_does_not_repeat_notifications(self):
        for index in range(20):
            self.add_participant(index, 95 if index == 0 else 80)
        settlement, created = settle_sponsored_view_assessment(self.assessment.id, SETTLEMENT_DAY)
        self.assertTrue(created)
        self.assertEqual(settlement.primary_winner_count, 1)
        self.assertEqual(settlement.secondary_winner_count, 1)
        self.assertEqual(settlement.awards.filter(selection='secondary').count(), 1)
        notification_count = Notification.objects.filter(action_url='/rewards').count()
        repeated, created_again = settle_sponsored_view_assessment(self.assessment.id, SETTLEMENT_DAY)
        self.assertFalse(created_again)
        self.assertEqual(repeated.id, settlement.id)
        self.assertEqual(Notification.objects.filter(action_url='/rewards').count(), notification_count)

    def test_unverified_flagged_and_ineligible_entries_do_not_generate_revenue(self):
        self.add_participant(1, 100, verified=False)
        self.add_participant(2, 100, flagged=True)
        _refunded_user, refunded_payment = self.add_participant(12, 100)
        refunded_payment.status = 'refunded'
        refunded_payment.save(update_fields=('status',))
        for index in range(3, 12):
            self.add_participant(index, 50)
        settlement, _ = settle_sponsored_view_assessment(self.assessment.id, SETTLEMENT_DAY)
        self.assertEqual(settlement.eligible_participant_count, 9)
        self.assertEqual(settlement.total_revenue_kes, 180)
        self.assertEqual(settlement.rewards_budget_kes, 90)
        self.assertEqual(settlement.awards.count(), 0)
        self.assertEqual(settlement.unallocated_reserve_kes, 90)

    def test_claim_is_owner_scoped_requires_consent_and_only_admin_can_review(self):
        student = None
        for index in range(200, 210):
            user, _payment = self.add_participant(index, 100 if index == 200 else 80)
            student = user if index == 200 else student
        settlement, _ = settle_sponsored_view_assessment(self.assessment.id, SETTLEMENT_DAY)
        claim = settlement.awards.get().claim
        client = APIClient()
        client.force_authenticate(student)
        url = reverse('submit-sponsored-reward-claim', kwargs={'claim_id': claim.id})
        no_consent = client.post(url, {'payment_method': 'mpesa', 'consent': False}, format='json')
        self.assertEqual(no_consent.status_code, 400)
        submitted = client.post(url, {'payment_method': 'mpesa', 'consent': True}, format='json')
        self.assertEqual(submitted.status_code, 200)
        self.assertEqual(submitted.data['status'], 'claim_submitted')
        self.assertNotIn('destination_phone', submitted.data)
        self.assertEqual(client.get(reverse('admin-reward-claims')).status_code, 403)

    def test_monthly_cash_award_only_accepts_the_two_published_amounts(self):
        program = SupportProgram(
            title='Monthly merit award', description='Merit sponsorship.',
            program_type='cash_award', eligibility_rules='Meet the cutoff.', merit_cutoff=80,
            award_amount_kes=20000,
        )
        program.full_clean()
        program.award_amount_kes = 25000
        with self.assertRaises(ValidationError):
            program.full_clean()

    def test_unconfigured_payout_adapter_never_reports_success(self):
        with self.assertRaises(PayoutProviderNotConfigured):
            get_reward_payout_provider().transfer(
                idempotency_key='award-id', recipient_phone='0712345678', amount_kes=100,
            )

    def test_failed_settlement_is_recorded_and_can_be_retried_without_partial_awards(self):
        for index in range(10):
            self.add_participant(index, 95)
        with patch('apps.cohorts.reward_settlement.send_notification', side_effect=RuntimeError('notification store unavailable')):
            with self.assertRaises(RuntimeError):
                settle_sponsored_view_assessment(self.assessment.id, SETTLEMENT_DAY)
        failed = SponsoredViewDailySettlement.objects.get(
            assessment=self.assessment, settlement_date=SETTLEMENT_DAY,
        )
        self.assertEqual(failed.status, 'failed')
        self.assertEqual(failed.attempt_count, 1)
        self.assertEqual(failed.awards.count(), 0)

        finalized, created = settle_sponsored_view_assessment(self.assessment.id, SETTLEMENT_DAY)
        self.assertTrue(created)
        self.assertEqual(finalized.status, 'finalized')
        self.assertEqual(finalized.attempt_count, 2)
        self.assertEqual(finalized.awards.count(), 1)

    def test_refund_after_settlement_records_adjustment_and_reverses_unpaid_award(self):
        for index in range(10):
            self.add_participant(index, 95)
        settlement, _ = settle_sponsored_view_assessment(self.assessment.id, SETTLEMENT_DAY)
        award = settlement.awards.get()
        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.post(
            reverse('sponsored-view-payment-admin-decision', kwargs={'payment_id': award.payment_id}),
            {'status': 'refunded', 'rejection_reason': 'Provider confirmed a refund.', 'refund_reference': 'REFUND-REWARD-1'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        adjustment = SponsoredViewSettlementAdjustment.objects.get(payment_id=award.payment_id)
        self.assertEqual(adjustment.revenue_reversal_kes, 20)
        self.assertEqual(adjustment.platform_share_reversal_kes, 10)
        self.assertEqual(adjustment.rewards_share_reversal_kes, 10)
        self.assertEqual(adjustment.refund_reference, 'REFUND-REWARD-1')
        self.assertEqual(adjustment.award_reversal_kes, 100)
        award.refresh_from_db()
        self.assertEqual(award.status, 'reversed')
        self.assertEqual(settlement.total_revenue_kes, 200)
