# Generated by Django 5.1.3 on 2025-01-17 16:35

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('competitions', '0011_competition_facebook_url_competition_instagram_url'),
    ]

    operations = [
        migrations.CreateModel(
            name='TshirtSize',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('size', models.CharField(choices=[('XS', 'Extra Small'), ('S', 'Small'), ('M', 'Medium'), ('L', 'Large'), ('XL', 'Extra Large'), ('XXL', '2X Large'), ('XXXL', '3X Large')], max_length=5, unique=True)),
            ],
        ),
        migrations.AddField(
            model_name='competition',
            name='provides_shirts',
            field=models.BooleanField(default=False, help_text='Check this box if T-shirts will be provided to participants.'),
        ),
        migrations.AddField(
            model_name='athletecompetition',
            name='tshirt_size',
            field=models.ForeignKey(blank=True, help_text='T-shirt size for the participant (if applicable).', null=True, on_delete=django.db.models.deletion.SET_NULL, to='competitions.tshirtsize'),
        ),
    ]
