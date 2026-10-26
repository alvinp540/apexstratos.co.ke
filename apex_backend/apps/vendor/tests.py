from datetime import timedelta
from tempfile import TemporaryDirectory

from django.urls import reverse
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.vendor.campaign_views import contest_sponsor_attributions, record_contest_campaign_event
from apps.vendor.models import (
    CampaignApproval,
    CampaignEvent,
    SponsorshipCampaign,
    VendorProfile,
    VendorVerification,
)
from apps.vendor.private_storage import vendor_verification_storage


class VendorCampaignModuleTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email='vendor-admin@example.test',
            username='vendor-admin',
            password='Admin-Test-Password-801!',
            role='admin',
            is_staff=True,
        )
        self.vendor_user = User.objects.create_user(
            email='campaign-vendor@example.test',
            username='campaign-vendor',
            password='Vendor-Test-Password-801!',
            role='vendor',
        )
        self.vendor = VendorProfile.objects.create(
            user=self.vendor_user,
            business_name='Example Learning Sponsor',
            description='A sponsor for learning programmes.',
            category='education',
            contact_name='Vendor Contact',
            contact_email='contact@example.test',
            contact_phone='+254700000001',
            location='Nairobi',
            status='approved',
        )
        self.client.force_authenticate(self.vendor_user)

    def campaign_payload(self, **overrides):
        today = timezone.localdate()
        values = {
            'name': 'Learning campaign',
            'objectives': 'Support learners with disclosed educational material.',
            'target_audience': 'Authenticated Apex learners',
            'eligibility_rules': {'regions': ['Kenya']},
            'campaign_type': 'learning_initiative',
            'study_area': 'Software Development',
            'target_content_ids': [],
            'description': 'A clear description of the proposed sponsorship.',
            'sponsor_disclosure': 'Sponsored by Example Learning Sponsor.',
            'start_date': today.isoformat(),
            'end_date': (today + timedelta(days=14)).isoformat(),
            'target_views': 500,
            'budget_amount': '5000.00',
            'currency': 'KES',
        }
        values.update(overrides)
        return values

    def create_submitted_campaign(self):
        created = self.client.post(
            reverse('vendor-campaign-list'),
            self.campaign_payload(),
            format='json',
        )
        self.assertEqual(created.status_code, 201, created.data)
        campaign_id = created.data['id']
        submitted = self.client.post(reverse('vendor-campaign-submit', kwargs={'campaign_id': campaign_id}))
        self.assertEqual(submitted.status_code, 200, submitted.data)
        return SponsorshipCampaign.objects.get(id=campaign_id)

    def test_unapproved_vendor_cannot_create_campaign(self):
        self.vendor.status = 'pending'
        self.vendor.save(update_fields=('status',))

        response = self.client.post(
            reverse('vendor-campaign-list'),
            self.campaign_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(SponsorshipCampaign.objects.count(), 0)

    def test_campaign_eligibility_rules_must_be_a_bounded_json_object(self):
        response = self.client.post(
            reverse('vendor-campaign-list'),
            self.campaign_payload(eligibility_rules=['not', 'an', 'object']),
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('eligibility_rules', response.data)

    def test_vendor_can_submit_draft_and_admin_approval_activates_campaign(self):
        campaign = self.create_submitted_campaign()
        self.assertEqual(campaign.status, 'pending_approval')
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            reverse('admin-campaign-decision', kwargs={'campaign_id': campaign.id}),
            {'decision': 'approve', 'feedback': 'Approved for the requested dates.'},
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.data)
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, 'active')
        self.assertEqual(campaign.reviewed_by, self.admin)
        self.assertEqual(campaign.approved_budget_amount, campaign.budget_amount)
        self.assertFalse(campaign.budget_tracking_enabled)
        self.assertTrue(CampaignApproval.objects.filter(campaign=campaign, decision='approved').exists())

    def test_campaign_changes_requested_is_a_distinct_resubmittable_state(self):
        campaign = self.create_submitted_campaign()
        self.client.force_authenticate(self.admin)
        decision = self.client.post(
            reverse('admin-campaign-decision', kwargs={'campaign_id': campaign.id}),
            {'decision': 'changes_requested', 'feedback': 'Clarify the audience.'},
            format='json',
        )
        self.assertEqual(decision.status_code, 200, decision.data)
        self.assertEqual(decision.data['status'], 'changes_requested')

        self.client.force_authenticate(self.vendor_user)
        updated = self.client.patch(
            reverse('vendor-campaign-detail', kwargs={'campaign_id': campaign.id}),
            {'description': 'Revised campaign proposal with clarified audience.'},
            format='json',
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(updated.data['status'], 'draft')
        self.assertEqual(updated.data['admin_feedback'], '')
        resubmitted = self.client.post(reverse('vendor-campaign-submit', kwargs={'campaign_id': campaign.id}))
        self.assertEqual(resubmitted.status_code, 200, resubmitted.data)
        self.assertEqual(resubmitted.data['status'], 'pending_approval')

    def test_vendor_cannot_activate_campaign_or_change_approved_budget(self):
        campaign = self.create_submitted_campaign()
        direct_activation = self.client.patch(
            reverse('vendor-campaign-detail', kwargs={'campaign_id': campaign.id}),
            {'status': 'active', 'approved_budget_amount': '1.00', 'budget_tracking_enabled': True},
            format='json',
        )
        self.assertEqual(direct_activation.status_code, 400, direct_activation.data)
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, 'pending_approval')
        self.assertIsNone(campaign.approved_budget_amount)
        self.assertFalse(campaign.budget_tracking_enabled)

        action = self.client.post(
            reverse('vendor-campaign-action', kwargs={'campaign_id': campaign.id}),
            {'action': 'activate'},
            format='json',
        )
        self.assertEqual(action.status_code, 400)
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, 'pending_approval')

    def test_suspending_vendor_pauses_live_campaign_and_reactivation_requires_admin_resume(self):
        campaign = self.create_submitted_campaign()
        self.client.force_authenticate(self.admin)
        campaign_approval = self.client.post(
            reverse('admin-campaign-decision', kwargs={'campaign_id': campaign.id}),
            {'decision': 'approve'},
            format='json',
        )
        self.assertEqual(campaign_approval.status_code, 200, campaign_approval.data)

        suspension = self.client.post(
            reverse('admin-vendor-decision', kwargs={'vendor_id': self.vendor.id}),
            {'status': 'suspended', 'feedback': 'Verification follow-up required.'},
            format='json',
        )
        self.assertEqual(suspension.status_code, 200, suspension.data)
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, 'paused')
        self.assertTrue(CampaignApproval.objects.filter(campaign=campaign, decision='paused').exists())

        reactivation = self.client.post(
            reverse('admin-vendor-decision', kwargs={'vendor_id': self.vendor.id}),
            {'status': 'reactivated'},
            format='json',
        )
        self.assertEqual(reactivation.status_code, 200, reactivation.data)
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, 'paused')

    def test_vendor_cannot_read_another_vendors_campaign_or_report(self):
        campaign = self.create_submitted_campaign()
        other_user = User.objects.create_user(
            email='other-vendor@example.test',
            username='other-vendor',
            password='Other-Test-Password-801!',
            role='vendor',
        )
        other_profile = VendorProfile.objects.create(
            user=other_user,
            business_name='Other Sponsor',
            description='Another vendor.',
            category='technology',
            contact_name='Other Contact',
            contact_email='other@example.test',
            contact_phone='+254700000002',
            location='Nairobi',
            status='approved',
        )
        campaign.vendor = other_profile
        campaign.save(update_fields=('vendor',))

        detail = self.client.get(reverse('vendor-campaign-detail', kwargs={'campaign_id': campaign.id}))
        report = self.client.get(reverse('vendor-campaign-report', kwargs={'campaign_id': campaign.id}))

        self.assertEqual(detail.status_code, 404)
        self.assertEqual(report.status_code, 404)

    def test_campaign_views_and_clicks_are_server_recorded_and_deduplicated(self):
        campaign = self.create_submitted_campaign()
        self.client.force_authenticate(self.admin)
        self.client.post(
            reverse('admin-campaign-decision', kwargs={'campaign_id': campaign.id}),
            {'decision': 'approve'},
            format='json',
        )
        self.client.force_authenticate(self.vendor_user)
        vendor_click = self.client.post(
            reverse('campaign-event', kwargs={'campaign_id': campaign.id}),
            {'event_type': 'click'},
            format='json',
        )
        self.assertEqual(vendor_click.status_code, 403)
        learner = User.objects.create_user(
            email='campaign-learner@example.test',
            username='campaign-learner',
            password='Learner-Test-Password-801!',
        )
        self.client.force_authenticate(learner)
        self.client.post(
            reverse('campaign-event', kwargs={'campaign_id': campaign.id}),
            {'event_type': 'click'},
            format='json',
        )

        self.assertEqual(CampaignEvent.objects.filter(campaign=campaign, event_type='click').count(), 1)

    def test_unique_views_report_after_privacy_threshold_and_deduplicates_reloads(self):
        campaign = self.create_submitted_campaign()
        self.client.force_authenticate(self.admin)
        self.client.post(
            reverse('admin-campaign-decision', kwargs={'campaign_id': campaign.id}),
            {'decision': 'approve'},
            format='json',
        )
        for index in range(5):
            viewer = User.objects.create_user(
                email=f'campaign-viewer-{index}@example.test',
                username=f'campaign-viewer-{index}',
                password='Viewer-Test-Password-801!',
            )
            self.client.force_authenticate(viewer)
            self.client.get(reverse('active-campaign-list'))
            self.client.get(reverse('active-campaign-list'))
        self.client.force_authenticate(self.vendor_user)

        report = self.client.get(reverse('vendor-campaign-report', kwargs={'campaign_id': campaign.id}))
        self.assertEqual(report.status_code, 200)
        self.assertFalse(report.data['suppressed'])
        self.assertEqual(report.data['recorded_authenticated_unique_views'], 5)
        self.assertEqual(report.data['recorded_activity_by_day'][0]['event_type'], 'view')
        self.assertEqual(report.data['recorded_activity_by_day'][0]['count'], 5)
        self.assertEqual(CampaignEvent.objects.filter(campaign=campaign, event_type='view').count(), 5)

    def test_contest_sponsorship_is_disclosed_and_completion_event_is_deduplicated(self):
        campaign = self.create_submitted_campaign()
        campaign.campaign_type = 'contest'
        campaign.target_content_ids = ['contest-assessment-1']
        campaign.save(update_fields=('campaign_type', 'target_content_ids'))
        self.client.force_authenticate(self.admin)
        approval = self.client.post(
            reverse('admin-campaign-decision', kwargs={'campaign_id': campaign.id}),
            {'decision': 'approve'},
            format='json',
        )
        self.assertEqual(approval.status_code, 200, approval.data)

        from types import SimpleNamespace
        assessment = SimpleNamespace(
            id='contest-assessment-1',
            pk='contest-assessment-1',
            field=campaign.study_area,
        )
        disclosures = contest_sponsor_attributions([assessment])
        self.assertEqual(disclosures['contest-assessment-1'][0]['sponsor_disclosure'], campaign.sponsor_disclosure)
        self.assertEqual(disclosures['contest-assessment-1'][0]['eligibility_rules'], campaign.eligibility_rules)

        learner = User.objects.create_user(
            email='contest-learner@example.test',
            username='contest-learner',
            password='Contest-Test-Password-801!',
        )
        record_contest_campaign_event(learner, assessment)
        record_contest_campaign_event(learner, assessment)
        self.assertEqual(
            CampaignEvent.objects.filter(campaign=campaign, event_type='assessment_completion').count(),
            1,
        )

    def test_public_registration_still_cannot_grant_admin_and_only_admin_can_review_campaign(self):
        self.client.force_authenticate(user=None)
        registration = self.client.post(
            '/api/v1/auth/register/',
            {
                'email': 'self-admin@example.test',
                'username': 'self-admin',
                'password': 'Unique-Test-Password-801!',
                'password2': 'Unique-Test-Password-801!',
                'role': 'admin',
            },
            format='json',
        )
        self.assertEqual(registration.status_code, 400)

        self.client.force_authenticate(self.vendor_user)
        campaign = self.create_submitted_campaign()
        admin_list = self.client.get(reverse('admin-campaign-list'))
        admin_decision = self.client.post(
            reverse('admin-campaign-decision', kwargs={'campaign_id': campaign.id}),
            {'decision': 'approve'},
            format='json',
        )

        self.assertEqual(admin_list.status_code, 403)
        self.assertEqual(admin_decision.status_code, 403)

    def test_professional_onboarding_creates_pending_vendor_and_never_grants_admin(self):
        applicant = User.objects.create_user(
            email='new-vendor@example.test',
            username='new-vendor',
            password='Vendor-Test-Password-802!',
            role='professional',
        )
        self.client.force_authenticate(applicant)
        response = self.client.post(
            reverse('vendor-onboarding'),
            {
                'business_name': 'New Vendor',
                'description': 'A vendor applying to sponsor learning.',
                'category': 'education',
                'contact_name': 'Applicant',
                'contact_email': 'applicant@example.test',
                'contact_phone': '+254700000002',
                'location': 'Nairobi',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.data)
        applicant.refresh_from_db()
        self.assertEqual(applicant.role, 'vendor')
        self.assertFalse(applicant.is_admin)
        self.assertEqual(response.data['status'], 'pending')
        self.assertEqual(VendorProfile.objects.get(user=applicant).status, 'pending')

    def test_verification_document_is_downloadable_only_through_admin_endpoint(self):
        old_location = vendor_verification_storage._location
        old_cached_location = vendor_verification_storage.__dict__.pop('location', None)
        with TemporaryDirectory() as private_root:
            vendor_verification_storage._location = private_root
            try:
                self.client.post(
                    reverse('vendor-verifications'),
                    {
                        'document_type': 'Business registration',
                        'document': SimpleUploadedFile(
                            'registration.pdf',
                            b'%PDF-1.4\nPrivate verification document',
                            content_type='application/pdf',
                        ),
                    },
                    format='multipart',
                )
                verification = VendorVerification.objects.get(vendor=self.vendor)
                self.assertNotIn('document', self.client.get(reverse('vendor-verifications')).data[0])

                vendor_download = self.client.get(
                    reverse('admin-vendor-verification-document', kwargs={'verification_id': verification.id})
                )
                self.assertEqual(vendor_download.status_code, 403)

                self.client.force_authenticate(self.admin)
                admin_download = self.client.get(
                    reverse('admin-vendor-verification-document', kwargs={'verification_id': verification.id})
                )
                self.assertEqual(admin_download.status_code, 200)
                self.assertIn('attachment', admin_download['Content-Disposition'])
                self.assertEqual(b''.join(admin_download.streaming_content), b'%PDF-1.4\nPrivate verification document')
            finally:
                vendor_verification_storage._location = old_location
                vendor_verification_storage.__dict__.pop('location', None)
                if old_cached_location is not None:
                    vendor_verification_storage.__dict__['location'] = old_cached_location
