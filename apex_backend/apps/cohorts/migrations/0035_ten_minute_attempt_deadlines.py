from datetime import timedelta

from django.db import migrations, models


def extend_active_attempt_deadlines(apps, schema_editor):
    models_to_extend = (
        apps.get_model('cohorts', 'TutorialAttempt'),
        apps.get_model('cohorts', 'AssessmentAttempt'),
        apps.get_model('cohorts', 'SponsoredViewAttempt'),
        apps.get_model('cohorts', 'AssessmentScheduleAttempt'),
    )
    for attempt_model in models_to_extend:
        for attempt in attempt_model.objects.filter(status='in_progress').only('pk', 'started_at'):
            updates = {'deadline_at': attempt.started_at + timedelta(seconds=600)}
            if attempt_model.__name__ == 'AssessmentScheduleAttempt':
                updates['duration_seconds'] = 600
            attempt_model.objects.filter(pk=attempt.pk).update(**updates)


class Migration(migrations.Migration):

    dependencies = [
        ('cohorts', '0034_sponsored_view_reward_tiers'),
    ]

    operations = [
        migrations.AlterField(
            model_name='assessmentscheduleattempt',
            name='duration_seconds',
            field=models.PositiveIntegerField(default=600),
        ),
        migrations.RunPython(extend_active_attempt_deadlines, migrations.RunPython.noop),
    ]
