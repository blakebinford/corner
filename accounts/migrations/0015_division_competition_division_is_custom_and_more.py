# Generated by Django 5.1.3 on 2025-01-26 17:50

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0014_weightclass_category'),
        ('competitions', '0019_result_event_rank'),
    ]

    operations = [
        migrations.AddField(
            model_name='division',
            name='competition',
            field=models.ForeignKey(blank=True, help_text='Competition this custom division belongs to.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='custom_divisions', to='competitions.competition'),
        ),
        migrations.AddField(
            model_name='division',
            name='is_custom',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='weightclass',
            name='competition',
            field=models.ForeignKey(blank=True, help_text='Competition this custom weight class belongs to.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='custom_weight_classes', to='competitions.competition'),
        ),
        migrations.AddField(
            model_name='weightclass',
            name='is_custom',
            field=models.BooleanField(default=False),
        ),
    ]
