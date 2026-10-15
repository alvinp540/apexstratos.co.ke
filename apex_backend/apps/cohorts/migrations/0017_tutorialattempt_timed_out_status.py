from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cohorts', '0016_supportapplication_supportapplicationevent_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='tutorialattempt',
            name='status',
            field=models.CharField(
                choices=[
                    ('in_progress', 'In Progress'),
                    ('graded', 'Graded'),
                    ('timed_out', 'Timed Out'),
                ],
                db_index=True,
                default='in_progress',
                max_length=16,
            ),
        ),
    ]
