import pandas as pd
import uuid
import csv
from pathlib import Path
from decimal import Decimal, InvalidOperation
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils.text import slugify
from django.utils.crypto import get_random_string
from django.db import models
from django.db.models import Q
from accounts.models import AthleteProfile
from competitions.models import AthleteCompetition, Competition, Division, WeightClass

User = get_user_model()


def clean_gender(value):
    if pd.isna(value):
        return None
    val = str(value).strip().lower()
    return val if val in ['male', 'female', 'other'] else None


class Command(BaseCommand):
    help = 'Bulk import athletes and register them to a competition.'

    def add_arguments(self, parser):
        parser.add_argument('excel_file', type=str)
        parser.add_argument('--competition', type=int, required=True)

    def handle(self, *args, **options):
        df = pd.read_excel(options['excel_file'])
        df.rename(columns=lambda x: x.strip().lower(), inplace=True)

        competition_id = options['competition']
        output_file = Path('imported_athletes.csv')

        try:
            competition = Competition.objects.get(pk=competition_id)
        except Competition.DoesNotExist:
            self.stderr.write(self.style.ERROR('Competition not found.'))
            return

        self.stdout.write(f"\n🏋️ Adding athletes to: {competition.name}\n")

        created_users = []

        for _, row in df.iterrows():
            first_name = str(row.get('firstname', '')).strip()
            last_name = str(row.get('lastname', '')).strip()
            gender = clean_gender(row.get('gender'))

            if not first_name or not last_name:
                self.stderr.write("❌ Skipping row with missing name.")
                continue

            if not gender:
                self.stderr.write(f"❌ Skipping {first_name} {last_name} – invalid or missing gender: {row.get('gender')}")
                continue

            # Age to DOB
            age_value = row.get('age')
            date_of_birth = None
            if pd.notna(age_value):
                try:
                    years = float(age_value)
                    days = int(years * 365.25)
                    date_of_birth = date.today() - timedelta(days=days)
                except Exception as e:
                    self.stderr.write(f"⚠️ {first_name} {last_name}: Invalid age '{age_value}' – {e}")

            # Social + Profile info
            instagram = str(row.get('instagram', '')).strip()
            nickname = str(row.get('nickname', '')).strip()
            coach = str(row.get('coach', '')).strip()
            home_gym = str(row.get('gym', '')).strip()
            city = str(row.get('city', '')).strip()
            state = str(row.get('state', '')).strip()
            division_name = str(row.get('division', '')).strip().lower()
            weight_class_str = row.get('weight class')

            # Generate username/password
            username_base = slugify(f"{first_name}-{last_name}")
            username = username_base or f"athlete-{uuid.uuid4().hex[:6]}"
            while User.objects.filter(username=username).exists():
                username = f"{username_base}-{uuid.uuid4().hex[:4]}"
            temp_password = get_random_string(length=12)

            # Create user
            user = User.objects.create_user(
                username=username,
                first_name=first_name,
                last_name=last_name,
                password=temp_password,
                date_of_birth=date_of_birth
            )
            if hasattr(user, 'role'):
                user.role = 'athlete'
            if hasattr(user, 'instagram_name'):
                user.instagram_name = instagram
            user.save()
            self.stdout.write(f"👤 Created user: {username} | DOB: {user.date_of_birth}")

            # Create AthleteProfile (raise error if it fails)
            try:
                profile = AthleteProfile.objects.create(
                    user=user,
                    gender=gender,
                    nickname=nickname or None,
                    coach=coach or None,
                    home_gym=home_gym or None,
                    city=city or None,
                    state=state or None
                )
                self.stdout.write(f"📄 Created profile for {username}")
            except Exception as e:
                raise RuntimeError(f"❌ Failed to create AthleteProfile for {username} – {e}")

            # Match Division
            division = Division.objects.filter(
                competition=competition
            ).filter(
                Q(predefined_name__iexact=division_name) |
                Q(custom_name__iexact=division_name)
            ).first()

            # Match WeightClass (decimal or single-class fallback)
            weight_class = None
            if division:
                try:
                    if pd.notna(weight_class_str) and str(weight_class_str).strip():
                        weight_value = Decimal(str(weight_class_str).strip())
                        weight_class = WeightClass.objects.filter(
                            name=weight_value,
                            gender__iexact=gender,
                            division=division,
                            division__competition=competition
                        ).first()
                    else:
                        weight_class = WeightClass.objects.filter(
                            name__isnull=True,
                            is_custom=True,
                            gender__iexact=gender,
                            division=division,
                            division__competition=competition
                        ).first()
                except (InvalidOperation, ValueError) as e:
                    self.stderr.write(
                        f"⚠️ {first_name} {last_name}: Invalid weight class format '{weight_class_str}' – {e}"
                    )

            if not division or not weight_class:
                self.stderr.write(
                    f"⚠️ {first_name} {last_name}: Could not match division '{division_name}' or weight class '{weight_class_str}'"
                )

            # Register for competition
            AthleteCompetition.objects.get_or_create(
                athlete=profile,
                competition=competition,
                defaults={
                    'division': division,
                    'weight_class': weight_class,
                }
            )

            self.stdout.write(f"✅ Registered {first_name} {last_name} ({username})")
            created_users.append({
                'Name': f"{first_name} {last_name}",
                'Username': username,
                'Password': temp_password
            })

        # Export credentials
        with open(output_file, mode='w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['Name', 'Username', 'Password'])
            writer.writeheader()
            writer.writerows(created_users)

        self.stdout.write(self.style.SUCCESS(f"\n✅ Import complete. Credentials saved to: {output_file.resolve()}"))
