# Generated by Django 5.1.3 on 2025-01-03 16:42

import django.db.models.functions.comparison
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0009_alter_weightclass_options'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='weightclass',
            options={'ordering': [django.db.models.functions.comparison.Cast(django.db.models.functions.comparison.Coalesce('name', models.Value(0)), output_field=models.DecimalField())]},
        ),
    ]