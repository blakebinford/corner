# Generated by Django 5.1.3 on 2025-01-03 15:59

import django.db.models.functions.comparison
import django.db.models.functions.text
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('competitions', '0005_seed_database'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='divisionweightclass',
            options={'ordering': ['division__name', 'gender', django.db.models.functions.comparison.Cast(django.db.models.functions.comparison.Coalesce(models.Case(models.When(then=django.db.models.functions.text.Substr('weight_class__name', 1, length=3), weight_class__name__endswith='+'), default='weight_class__name'), models.Value('0')), output_field=models.DecimalField())]},
        ),
    ]