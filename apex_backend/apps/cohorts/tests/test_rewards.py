from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.cohorts.models import (
    SponsoredViewAssessment,
    SponsoredViewAttempt,
    SponsoredViewDailySettlement,
    SponsoredViewPayment,
    SponsoredViewQuestion,
    SponsoredViewRewardAward,
    SponsoredViewRewardCycle,
    SponsoredViewRewardCycleEntry,
    SponsoredViewSettlementAdjustment,
    SupportProgram,
)
from apps.cohorts.payouts import PayoutProviderNotConfigured, get_reward_payout_provider
from apps.cohorts.reward_cycles import record_sponsored_view_completion, retry_failed_sponsored_reward_cycles
from apps.notifications.models import Notification


EAT = ZoneInfo('Africa/Nairobi')
STARTED_AT = datetime(2026, 10, 12, 10, tzinfo=EAT)


class SponsoredRewardCycleTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email='rewards-admin@example.test', username='rewards-admin',
            password='test-password', role='admin', is_staff=True,
        )
        self.assessment = SponsoredViewAssessment.objects.create(
            week=1, slot=8, field='Software Development', title='Cycle reward test',
            description='Assessment used to test ten-completion reward cycles.',
            learning_objectives=['A', 'B', 'C'], status='published',
        )
        for order in range(1, 11):
            SponsoredViewQuestion.objects.create(
                assessment=self.assessment, order=order, prompt=f'Question {order}',
                options=['A', 'B'], correct_answer='A', rationale='Test rationale',
            )

    def add_participant(self, index, score, *, status='graded', verified=True, flagged=False, offset=None):
        user = User.objects.create_user(
            email=f'reward-student-{index}@example.test',
            username=f'reward-student-{index}', password='test-password',
            phone_number=f'071234{index:04d}',
        )
        submitted_at = STARTED_AT + timedelta(seconds=offset if offset is not None else index)
        payment = SponsoredViewPayment.objects.create(
            user=user, assessment=self.assessment, amount_kes=20,
            payment_reference=f'REWARD-PAY-{index}',
            mpesa_transaction_id=f'REWARD-TXN-{index}' if verified else '',
            status='verified' if verified else 'pending',
            verified_at=STARTED_AT if verified else None,
        )
        attempt = SponsoredViewAttempt.objects.create(
            payment=payment, user=user, assessment=self.assessment,
            question_snapshot=[], answers={}, score=score, status=status,
            started_at=STARTED_AT - timedelta(minutes=5),
            deadline_at=STARTED_AT,
            submitted_at=submitted_at,
            is_flagged=flagged,
        )
        return user, payment, attempt

    def complete(self, index, score, **kwargs):
        _user, _payment, attempt = self.add_participant(index, score, **kwargs)
        return record_sponsored_view_completion(attempt.id)

    def test_nine_completions_stay_open_and_tenth_finalizes_fifty_fifty_award(self):
        for index in range(9):
            cycle = self.complete(index, 70 + index)
        self.assertEqual(cycle.status, 'open')
        self.assertEqual(cycle.eligible_completion_count, 9)
        self.assertFalse(SponsoredViewDailySettlement.objects.exists())

        cycle = self.complete(9, 95)
        cycle.refresh_from_db()
        self.assertEqual(cycle.status, 'finalized')
        self.assertEqual(cycle.eligible_completion_count, 10)
        self.assertEqual(cycle.gross_revenue_kes, 200)
        self.assertEqual(cycle.platform_allocation_kes, 100)
        self.assertEqual(cycle.rewards_allocation_kes, 100)
        self.assertEqual(cycle.award_amount_kes, 100)
        self.assertEqual(cycle.winner.username, 'reward-student-9')
        self.assertEqual(cycle.entries.count(), 10)
        self.assertEqual(SponsoredViewRewardAward.objects.filter(reward_cycle=cycle).count(), 1)
        self.assertTrue(SponsoredViewRewardAward.objects.get(reward_cycle=cycle).claim)

    def test_timed_out_attempt_can_count_and_duplicate_processing_is_idempotent(self):
        completed = []
        for index in range(10):
            completed.append(self.add_participant(index, 90, status='timed_out'))
        cycle = record_sponsored_view_completion(completed[-1][2].id)
        for _user, _payment, attempt in completed[:-1]:
            record_sponsored_view_completion(attempt.id)
        cycle.refresh_from_db()
        self.assertEqual(cycle.status, 'finalized')
        self.assertEqual(cycle.entries.count(), 10)
        self.assertEqual(SponsoredViewRewardAward.objects.filter(reward_cycle=cycle).count(), 1)
        self.assertEqual(Notification.objects.filter(action_url='/rewards').count(), 1)

    def test_highest_eligible_score_wins_and_ties_use_submission_then_user_id(self):
        first_user, _payment, first_attempt = self.add_participant(1, 95, offset=1)
        second_user, _payment, second_attempt = self.add_participant(2, 95, offset=1)
        first = record_sponsored_view_completion(first_attempt.id)
        tied_users = sorted((first_user, second_user), key=lambda user: str(user.id))
        record_sponsored_view_completion(second_attempt.id)
        for index in range(3, 11):
            self.complete(index, 80)
        first.refresh_from_db()
        self.assertEqual(first.winner_id, tied_users[0].id)
        self.assertEqual(first.ranking_snapshot[0]['user_id'], str(first.winner_id))

    def test_eleventh_completion_belongs_to_the_next_cycle(self):
        first_cycle = None
        for index in range(10):
            first_cycle = self.complete(index, 90)
        second_cycle = self.complete(10, 90)
        self.assertEqual(first_cycle.cycle_number, 1)
        self.assertEqual(second_cycle.cycle_number, 2)
        self.assertEqual(second_cycle.status, 'open')
        self.assertEqual(second_cycle.eligible_completion_count, 1)
        self.assertEqual(first_cycle.entries.count(), 10)

    def test_pending_payment_or_flagged_attempt_does_not_create_cycle_entry(self):
        _user, _payment, pending = self.add_participant(1, 99, verified=False)
        _user, _payment, flagged = self.add_participant(2, 99, flagged=True)
        self.assertIsNone(record_sponsored_view_completion(pending.id))
        self.assertIsNone(record_sponsored_view_completion(flagged.id))
        self.assertFalse(SponsoredViewRewardCycle.objects.exists())

    def test_no_eligible_merit_creates_audited_exception_and_keeps_reward_allocation_in_reserve(self):
        for index in range(10):
            cycle = self.complete(index, 69)
        cycle.refresh_from_db()
        settlement = cycle.settlement_record
        self.assertEqual(cycle.status, 'exception')
        self.assertIsNone(cycle.winner_id)
        self.assertEqual(settlement.total_revenue_kes, 200)
        self.assertEqual(settlement.platform_share_kes, 100)
        self.assertEqual(settlement.rewards_budget_kes, 100)
        self.assertEqual(settlement.unallocated_reserve_kes, 100)
        self.assertEqual(SponsoredViewRewardAward.objects.filter(reward_cycle=cycle).count(), 0)
        self.assertTrue(Notification.objects.filter(user=self.admin).exists())

    def test_finalization_failure_is_retryable_without_duplicate_awards_or_notifications(self):
        for index in range(9):
            self.complete(index, 90)
        _user, _payment, attempt = self.add_participant(9, 95)
        with patch('apps.cohorts.reward_cycles.send_notification', side_effect=RuntimeError('notification store unavailable')):
            failed = record_sponsored_view_completion(attempt.id)
        self.assertEqual(failed.status, 'failed')
        self.assertEqual(failed.entries.count(), 10)
        retried = retry_failed_sponsored_reward_cycles()
        self.assertEqual(retried[0].status, 'finalized')
        self.assertEqual(SponsoredViewRewardAward.objects.filter(reward_cycle=failed).count(), 1)
        self.assertEqual(Notification.objects.filter(action_url='/rewards').count(), 1)

    def test_refund_after_finalization_records_cycle_adjustment_and_reverses_award(self):
        cycle = None
        for index in range(10):
            cycle = self.complete(index, 95)
        award = SponsoredViewRewardAward.objects.get(reward_cycle=cycle)
        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.post(
            reverse('sponsored-view-payment-admin-decision', kwargs={'payment_id': award.payment_id}),
            {'status': 'refunded', 'rejection_reason': 'Provider confirmed a refund.', 'refund_reference': 'CYCLE-REFUND-1'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        adjustment = SponsoredViewSettlementAdjustment.objects.get(payment_id=award.payment_id)
        self.assertEqual(adjustment.reward_cycle_id, cycle.id)
        self.assertEqual(adjustment.revenue_reversal_kes, 20)
        self.assertEqual(adjustment.platform_share_reversal_kes, 10)
        self.assertEqual(adjustment.rewards_share_reversal_kes, 10)
        award.refresh_from_db()
        self.assertEqual(award.status, 'reversed')
        self.assertEqual(cycle.gross_revenue_kes, 200)

    def test_monthly_cash_award_only_accepts_the_two_published_amounts(self):
        program = SupportProgram(
            title='Monthly merit award', description='Merit sponsorship.',
            program_type='cash_award', eligibility_rules='Meet the cutoff.', merit_cutoff=80,
            award_amount_kes=20000,
        )
        program.full_clean()
        program.award_amount_kes = 25000
        with self.assertRaises(Exception):
            program.full_clean()

    def test_unconfigured_payout_adapter_never_reports_success(self):
        with self.assertRaises(PayoutProviderNotConfigured):
            get_reward_payout_provider().transfer(
                idempotency_key='award-id', recipient_phone='0712345678', amount_kes=100,
            )
