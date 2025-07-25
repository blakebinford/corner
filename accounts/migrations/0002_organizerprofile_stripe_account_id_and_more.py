# Generated by Django 5.1.7 on 2025-05-24 18:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='organizerprofile',
            name='stripe_account_id',
            field=models.CharField(blank=True, help_text='ID of the connected Stripe account', max_length=64, null=True),
        ),
        migrations.AlterField(
            model_name='athleteprofile',
            name='height',
            field=models.IntegerField(blank=True, help_text="Athlete's height in inches", null=True),
        ),
    ]
