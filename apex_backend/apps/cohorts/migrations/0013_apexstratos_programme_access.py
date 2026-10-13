import uuid
from django.conf import settings
from django.db import migrations, models
from django.db.models import Count
import django.db.models.deletion


FIELD_LABELS = {
    'Engineering': 'General Engineering',
    'Medical & Health': 'Medical and Health',
    'Business & AI': 'Business and the AI Revolution',
    'Law & Society': 'Law and Society',
    'Media & Arts': 'Media and Arts',
}


def normalize_existing_values(apps, schema_editor):
    for model_name, field_name in (
        ('Cohort', 'profession'),
        ('Tutorial', 'field'),
        ('AssessmentSchedule', 'field'),
        ('ParticipationPayment', 'field'),
    ):
        model = apps.get_model('cohorts', model_name)
        for old_value, new_value in FIELD_LABELS.items():
            model.objects.filter(**{field_name: old_value}).update(**{field_name: new_value})

    for app_label, model_name in (('profiles', 'Profile'), ('rankings', 'Ranking')):
        model = apps.get_model(app_label, model_name)
        for old_value, new_value in FIELD_LABELS.items():
            model.objects.filter(profession=old_value).update(profession=new_value)

    Attempt = apps.get_model('cohorts', 'AssessmentScheduleAttempt')
    duplicate_attempts = list(
        Attempt.objects.values('user_id', 'assessment_id')
        .annotate(record_count=Count('id'))
        .filter(record_count__gt=1)
        .values_list('user_id', 'assessment_id')[:5]
    )
    if duplicate_attempts:
        raise RuntimeError(
            'Cannot enforce one contest attempt per student and assessment; duplicate existing attempts include '
            f'{duplicate_attempts!r}. Resolve them through an audited process, then retry the migration.'
        )

    Payment = apps.get_model('cohorts', 'ParticipationPayment')
    for field_name in ('payment_reference', 'mpesa_transaction_id'):
        duplicates = list(
            Payment.objects.exclude(**{f'{field_name}__isnull': True})
            .exclude(**{field_name: ''})
            .values(field_name)
            .annotate(record_count=Count('id'))
            .filter(record_count__gt=1)
            .values_list(field_name, flat=True)[:5]
        )
        if duplicates:
            raise RuntimeError(
                f'Cannot add unique {field_name} constraint; duplicate existing values include {duplicates!r}. '
                'Resolve these records through an audited data-cleanup process, then retry the migration.'
            )
        Payment.objects.filter(**{field_name: ''}).update(**{field_name: None})


def restore_empty_payment_values(apps, schema_editor):
    Payment = apps.get_model('cohorts', 'ParticipationPayment')
    Payment.objects.filter(payment_reference__isnull=True).update(payment_reference='')
    Payment.objects.filter(mpesa_transaction_id__isnull=True).update(mpesa_transaction_id='')
    for model_name, field_name in (
        ('Cohort', 'profession'),
        ('Tutorial', 'field'),
        ('AssessmentSchedule', 'field'),
        ('ParticipationPayment', 'field'),
    ):
        model = apps.get_model('cohorts', model_name)
        for old_value, new_value in FIELD_LABELS.items():
            model.objects.filter(**{field_name: new_value}).update(**{field_name: old_value})
    for app_label, model_name in (('profiles', 'Profile'), ('rankings', 'Ranking')):
        model = apps.get_model(app_label, model_name)
        for old_value, new_value in FIELD_LABELS.items():
            model.objects.filter(profession=new_value).update(profession=old_value)


class Migration(migrations.Migration):
    dependencies = [
        ('cohorts', '0012_assessmentschedule_assessmentscheduleattempt_and_more'),
        ('profiles', '0001_initial'),
        ('rankings', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='participationpayment',
            name='full_name',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='participationpayment',
            name='phone_number',
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name='participationpayment',
            name='verification_notes',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='participationpayment',
            name='rejection_reason',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='assessmentscheduleattempt',
            name='assessment_snapshot',
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name='assessmentscheduleattempt',
            name='deadline_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='tutorial',
            name='field',
            field=models.CharField(
                choices=[
                    ('Software Development', 'Software Development'),
                    ('Computer Science', 'Computer Science'),
                    ('Finance', 'Finance'),
                    ('General Engineering', 'General Engineering'),
                    ('Medical and Health', 'Medical and Health'),
                    ('Business and the AI Revolution', 'Business and the AI Revolution'),
                    ('Law and Society', 'Law and Society'),
                    ('Media and Arts', 'Media and Arts'),
                    ('Education', 'Education'),
                    ('Entrepreneurship', 'Entrepreneurship'),
                ],
                db_index=True,
                max_length=40,
            ),
        ),
        migrations.AlterField(
            model_name='tutorial',
            name='status',
            field=models.CharField(
                choices=[
                    ('draft', 'Draft'),
                    ('in_review', 'In Review'),
                    ('approved', 'Approved'),
                    ('scheduled', 'Scheduled'),
                    ('published', 'Published'),
                    ('archived', 'Archived'),
                ],
                db_index=True,
                default='draft',
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name='assessmentschedule',
            name='field',
            field=models.CharField(
                choices=[
                    ('Software Development', 'Software Development'),
                    ('Computer Science', 'Computer Science'),
                    ('Finance', 'Finance'),
                    ('General Engineering', 'General Engineering'),
                    ('Medical and Health', 'Medical and Health'),
                    ('Business and the AI Revolution', 'Business and the AI Revolution'),
                    ('Law and Society', 'Law and Society'),
                    ('Media and Arts', 'Media and Arts'),
                    ('Education', 'Education'),
                    ('Entrepreneurship', 'Entrepreneurship'),
                ],
                db_index=True,
                max_length=40,
            ),
        ),
        migrations.AlterField(
            model_name='assessmentschedule',
            name='status',
            field=models.CharField(
                choices=[
                    ('draft', 'Draft'),
                    ('in_review', 'In Review'),
                    ('approved', 'Approved'),
                    ('scheduled', 'Scheduled'),
                    ('published', 'Published'),
                    ('archived', 'Archived'),
                ],
                db_index=True,
                default='draft',
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name='participationpayment',
            name='field',
            field=models.CharField(
                choices=[
                    ('Software Development', 'Software Development'),
                    ('Computer Science', 'Computer Science'),
                    ('Finance', 'Finance'),
                    ('General Engineering', 'General Engineering'),
                    ('Medical and Health', 'Medical and Health'),
                    ('Business and the AI Revolution', 'Business and the AI Revolution'),
                    ('Law and Society', 'Law and Society'),
                    ('Media and Arts', 'Media and Arts'),
                    ('Education', 'Education'),
                    ('Entrepreneurship', 'Entrepreneurship'),
                ],
                db_index=True,
                max_length=40,
            ),
        ),
        migrations.AlterField(
            model_name='participationpayment',
            name='payment_reference',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='participationpayment',
            name='mpesa_transaction_id',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='participationpayment',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending Verification'),
                    ('under_review', 'Under Review'),
                    ('verified', 'Verified'),
                    ('rejected', 'Rejected'),
                    ('expired', 'Expired'),
                    ('cancelled', 'Cancelled'),
                ],
                db_index=True,
                default='pending',
                max_length=20,
            ),
        ),
        migrations.RunPython(normalize_existing_values, restore_empty_payment_values),
        migrations.AlterField(
            model_name='participationpayment',
            name='payment_reference',
            field=models.CharField(blank=True, max_length=255, null=True, unique=True),
        ),
        migrations.AlterField(
            model_name='participationpayment',
            name='mpesa_transaction_id',
            field=models.CharField(blank=True, max_length=255, null=True, unique=True),
        ),
        migrations.CreateModel(
            name='ParticipationPaymentEvent',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('decision', models.CharField(choices=[('submitted', 'Submitted'), ('under_review', 'Under Review'), ('verified', 'Verified'), ('rejected', 'Rejected')], db_index=True, max_length=20)),
                ('notes', models.TextField(blank=True)),
                ('confirmed_transaction_id', models.CharField(blank=True, max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='participation_payment_events', to=settings.AUTH_USER_MODEL)),
                ('payment', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='events', to='cohorts.participationpayment')),
            ],
            options={
                'db_table': 'participation_payment_events',
                'ordering': ['created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='assessmentscheduleattempt',
            constraint=models.UniqueConstraint(
                fields=('user', 'assessment'),
                name='unique_schedule_attempt_per_user',
            ),
        ),
    ]
