from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cohorts', '0033_sponsoredviewrewardcycle_payout_status'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='sponsoredviewpayment',
            name='sponsored_view_price_is_20_kes',
        ),
        migrations.AddConstraint(
            model_name='sponsoredviewpayment',
            constraint=models.CheckConstraint(
                condition=models.Q(('amount_kes__in', (20, 40, 80, 160, 320))),
                name='sponsored_view_price_is_valid_tier',
            ),
        ),
        migrations.RemoveConstraint(
            model_name='sponsoredviewrewardcycle',
            name='unique_sponsored_reward_cycle_number',
        ),
        migrations.RemoveConstraint(
            model_name='sponsoredviewrewardcycle',
            name='unique_open_sponsored_reward_cycle',
        ),
        migrations.AddField(
            model_name='sponsoredviewrewardcycle',
            name='prize_amount_kes',
            field=models.PositiveSmallIntegerField(default=100),
        ),
        migrations.AlterField(
            model_name='sponsoredviewrewardcycle',
            name='award_amount_kes',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='sponsoredviewrewardcycle',
            name='financial_rule_version',
            field=models.CharField(default='10-completion-50-50-tiered-v1', max_length=32),
        ),
        migrations.AddConstraint(
            model_name='sponsoredviewrewardcycle',
            constraint=models.UniqueConstraint(
                fields=('assessment', 'participation_fee_kes', 'cycle_number'),
                name='unique_sponsored_reward_cycle_tier_number',
            ),
        ),
        migrations.AddConstraint(
            model_name='sponsoredviewrewardcycle',
            constraint=models.UniqueConstraint(
                condition=models.Q(('status', 'open')),
                fields=('assessment', 'participation_fee_kes'),
                name='unique_open_sponsored_reward_tier_cycle',
            ),
        ),
        migrations.AddConstraint(
            model_name='sponsoredviewrewardcycle',
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(('participation_fee_kes', 20), ('prize_amount_kes', 100))
                    | models.Q(('participation_fee_kes', 40), ('prize_amount_kes', 200))
                    | models.Q(('participation_fee_kes', 80), ('prize_amount_kes', 400))
                    | models.Q(('participation_fee_kes', 160), ('prize_amount_kes', 800))
                    | models.Q(('participation_fee_kes', 320), ('prize_amount_kes', 1600))
                ),
                name='sponsored_reward_cycle_valid_tier',
            ),
        ),
        migrations.AddConstraint(
            model_name='sponsoredviewrewardcycle',
            constraint=models.CheckConstraint(
                condition=models.Q(('target_completion_count', 10)),
                name='sponsored_reward_cycle_size_is_ten',
            ),
        ),
    ]
