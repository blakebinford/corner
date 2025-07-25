# Generated by Django 5.1.7 on 2025-06-01 21:03

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('competitions', '0010_eventimplementdefinition_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ImplementDefinition',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('base_weight', models.DecimalField(decimal_places=2, default=0, max_digits=6)),
                ('unit', models.CharField(choices=[('lbs', 'Pounds (lbs)'), ('kg', 'Kilograms (kg)')], default='lbs', max_length=3)),
                ('loading_points', models.PositiveSmallIntegerField(default=2)),
                ('organizer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='implements', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['name'],
                'unique_together': {('organizer', 'name')},
            },
        ),
        migrations.DeleteModel(
            name='EventImplementDefinition',
        ),
    ]
