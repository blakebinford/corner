# Generated by Django 5.1.7 on 2025-06-19 12:28

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('competitions', '0018_tshirtsize_style_alter_tshirtsize_size_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='competition',
            name='current_event',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='current_for_competitions', to='competitions.event'),
        ),
    ]
