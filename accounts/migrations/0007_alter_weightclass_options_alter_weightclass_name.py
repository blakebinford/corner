# Generated by Django 5.1.3 on 2025-01-03 16:06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_alter_weightclass_options_and_more'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='weightclass',
            options={},
        ),
        migrations.AlterField(
            model_name='weightclass',
            name='name',
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True),
        ),
    ]
