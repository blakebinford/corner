# Generated by Django 5.1.3 on 2024-12-29 21:07

import django.core.validators
import django.db.models.deletion
import tinymce.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('accounts', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='EventBase',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name='Federation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('logo', models.ImageField(upload_to='federation_logos/')),
            ],
        ),
        migrations.CreateModel(
            name='Sponsor',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('logo', models.ImageField(upload_to='sponsor_logos/')),
            ],
        ),
        migrations.CreateModel(
            name='Tag',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name='Competition',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('comp_date', models.DateField()),
                ('location', models.CharField(max_length=255)),
                ('start_time', models.TimeField(blank=True, null=True)),
                ('image', models.ImageField(blank=True, default='competition_images/default_competition_image2.jpg', null=True, upload_to='competition_images/')),
                ('capacity', models.PositiveIntegerField(default=100)),
                ('description', tinymce.models.HTMLField(blank=True)),
                ('event_location_name', models.CharField(blank=True, max_length=255)),
                ('comp_end_date', models.DateField(blank=True, null=True)),
                ('address', models.CharField(blank=True, max_length=255)),
                ('city', models.CharField(blank=True, max_length=255)),
                ('state', models.CharField(blank=True, max_length=255)),
                ('zip_code', models.CharField(blank=True, max_length=10)),
                ('liability_waiver', models.TextField(blank=True)),
                ('scoring_system', models.CharField(max_length=50)),
                ('status', models.CharField(choices=[('upcoming', 'Upcoming'), ('full', 'Full'), ('completed', 'Completed'), ('canceled', 'Canceled'), ('limited', 'Limited'), ('closed', 'Closed')], max_length=20)),
                ('registration_deadline', models.DateTimeField()),
                ('signup_price', models.DecimalField(decimal_places=2, default=0.0, max_digits=10, validators=[django.core.validators.MinValueValidator(0.0)])),
                ('allowed_divisions', models.ManyToManyField(related_name='allowed_competitions', to='accounts.division')),
                ('allowed_weight_classes', models.ManyToManyField(related_name='allowed_competitions', to='accounts.weightclass')),
                ('organizer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='organized_competitions', to=settings.AUTH_USER_MODEL)),
                ('federation', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='competitions.federation')),
                ('sponsor_logos', models.ManyToManyField(blank=True, to='competitions.sponsor')),
                ('tags', models.ManyToManyField(blank=True, related_name='competitions', to='competitions.tag')),
            ],
        ),
        migrations.CreateModel(
            name='CommentatorNote',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('note', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('athlete', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='accounts.athleteprofile')),
                ('commentator', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('competition', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='competitions.competition')),
            ],
        ),
        migrations.CreateModel(
            name='AthleteCompetition',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('registration_date', models.DateTimeField(auto_now_add=True)),
                ('payment_status', models.CharField(choices=[('pending', 'Pending'), ('canceled', 'Canceled'), ('refunded', 'Refunded'), ('paid', 'Paid')], max_length=20)),
                ('registration_status', models.CharField(choices=[('pending', 'Pending'), ('complete', 'Complete'), ('canceled', 'Canceled')], default='pending', max_length=20)),
                ('signed_up', models.BooleanField(default=False)),
                ('total_points', models.PositiveIntegerField(default=0)),
                ('rank', models.PositiveIntegerField(blank=True, null=True)),
                ('athlete', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='accounts.athleteprofile')),
                ('division', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='accounts.division')),
                ('weight_class', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='accounts.weightclass')),
                ('competition', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='competitions.competition')),
            ],
            options={
                'unique_together': {('athlete', 'competition')},
            },
        ),
        migrations.CreateModel(
            name='DivisionWeightClass',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('gender', models.CharField(blank=True, choices=[('male', 'Male'), ('female', 'Female')], max_length=10)),
                ('division', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='accounts.division')),
                ('weight_class', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='accounts.weightclass')),
            ],
            options={
                'unique_together': {('division', 'gender', 'weight_class')},
            },
        ),
        migrations.CreateModel(
            name='Event',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=80, unique=True)),
                ('weight_type', models.CharField(choices=[('time', 'Time'), ('distance', 'Distance'), ('max', 'Max Weight'), ('height', 'Height'), ('reps', 'Reps')], max_length=20)),
                ('event_base', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='competitions.eventbase')),
            ],
        ),
        migrations.CreateModel(
            name='EventImplement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('implement_name', models.CharField(blank=True, max_length=100)),
                ('implement_order', models.PositiveIntegerField(default=1)),
                ('weight', models.IntegerField()),
                ('weight_unit', models.CharField(choices=[('lbs', 'lbs'), ('kg', 'kg')], default='lbs', max_length=20)),
                ('division_weight_class', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='competitions.divisionweightclass')),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='implements', to='competitions.event')),
            ],
        ),
        migrations.CreateModel(
            name='EventOrder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order', models.PositiveIntegerField(default=1)),
                ('competition', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='competitions.competition')),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='competitions.event')),
            ],
            options={
                'ordering': ['order'],
            },
        ),
        migrations.AddField(
            model_name='event',
            name='competitions',
            field=models.ManyToManyField(related_name='events', through='competitions.EventOrder', to='competitions.competition'),
        ),
        migrations.CreateModel(
            name='Result',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('points_earned', models.PositiveIntegerField(default=0)),
                ('time', models.DurationField(blank=True, null=True)),
                ('value', models.CharField(blank=True, max_length=255)),
                ('athlete_competition', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='results', to='competitions.athletecompetition')),
                ('event_order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='competitions.eventorder')),
            ],
        ),
    ]