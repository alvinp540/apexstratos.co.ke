from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cohorts', '0019_sponsoredviewassessment_sponsoredviewpayment_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='supportapplication',
            name='status',
            field=models.CharField(
                choices=[
                    ('submitted', 'Submitted'),
                    ('under_review', 'Under Review'),
                    ('approved', 'Approved'),
                    ('awaiting_funding', 'Awaiting Funding'),
                    ('payment_processing', 'Payment Processing'),
                    ('paid', 'Paid'),
                    ('declined', 'Declined'),
                    ('awaiting_information', 'Awaiting Information'),
                ],
                db_index=True,
                default='submitted',
                max_length=24,
            ),
        ),
        migrations.AlterField(
            model_name='supportapplicationevent',
            name='status',
            field=models.CharField(
                choices=[
                    ('submitted', 'Submitted'),
                    ('under_review', 'Under Review'),
                    ('approved', 'Approved'),
                    ('awaiting_funding', 'Awaiting Funding'),
                    ('payment_processing', 'Payment Processing'),
                    ('paid', 'Paid'),
                    ('declined', 'Declined'),
                    ('awaiting_information', 'Awaiting Information'),
                ],
                max_length=24,
            ),
        ),
    ]
