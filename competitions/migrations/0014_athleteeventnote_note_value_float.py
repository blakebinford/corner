# Generated by Django 5.1.7 on 2025-06-14 16:27

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('competitions', '0013_event_description'),
    ]

    operations = [
        migrations.AddField(
            model_name='athleteeventnote',
            name='note_value_float',
            field=models.FloatField(blank=True, null=True),
        ),
    ]
