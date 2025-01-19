# Generated by Django 5.1.3 on 2025-01-19 01:15

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0013_alter_weightclass_unique_together'),
    ]

    operations = [
        migrations.AddField(
            model_name='weightclass',
            name='category',
            field=models.CharField(choices=[('lw', 'LW'), ('mw', 'MW'), ('hw', 'HW'), ('shw', 'SWH')], default='middleweight', help_text='Weight class category (e.g., lightweight, middleweight).', max_length=20),
        ),
    ]
