# Generated by Django 5.1.3 on 2025-01-03 16:47

import django.db.models.functions.comparison
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0010_alter_weightclass_options'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='weightclass',
            options={'ordering': [django.db.models.functions.comparison.Coalesce(django.db.models.functions.comparison.Cast('name', output_field=models.DecimalField()), models.Value(0))]},
        ),
    ]