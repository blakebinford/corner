# Generated by Django 5.1.7 on 2025-06-05 16:24

import tinymce.models
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('competitions', '0012_eventimplement_implement_definition'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='description',
            field=tinymce.models.HTMLField(blank=True, null=True),
        ),
    ]
