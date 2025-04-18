# Generated by Django 5.1.3 on 2025-02-17 14:42

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('competitions', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='weightclass',
            name='division',
            field=models.ForeignKey(blank=True, help_text='Division that this weight class belongs to.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='weight_classes', to='competitions.division'),
        ),
    ]
