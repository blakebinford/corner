import boto3
from openai import OpenAI
from collections import defaultdict
from competitions.models import AthleteCompetition, Competition, NationalsQualifier
from django.db.models import Count, Q
from django.db.utils import IntegrityError
from django.conf import settings
from django.core.exceptions import PermissionDenied

client = OpenAI(api_key=settings.OPENAI_API_KEY)


def generate_presigned_url(key, expires_in=3600):
    s3 = boto3.client(
        's3',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME,
    )

    return s3.generate_presigned_url(
        'get_object',
        Params={'Bucket': settings.AWS_STORAGE_BUCKET_NAME, 'Key': key},
        ExpiresIn=expires_in
    )


# competitions/utils.py
def get_onboarding_status(competition):
    """
    Returns which setup steps are complete:
      - details: key fields filled out
      - divisions: at least one allowed division assigned
      - events: at least one Event created
      - publish: publication_status == 'published'
    """
    return {
        'details': bool(
            competition.name
            and competition.comp_date
            and competition.registration_deadline
            and competition.city
            and competition.state
        ),
        'divisions': competition.allowed_divisions.exists(),
        'events': competition.events.exists(),
        'publish': competition.publication_status == 'published',
    }

def generate_short_description(competition):
    prompt = (
        f"Create a short, compelling summary (max 40 words) for a strength competition. No em dashes. Write in the voice of strongman athlete. Hyped but real.  \n\n"
        f"Name: {competition.name}\n"
        f"Date: {competition.comp_date.strftime('%B %d, %Y') if competition.comp_date else 'TBD'}\n"
        f"Location: {competition.city}, {competition.state} — {competition.event_location_name or 'TBD'}\n"
        f"Federation: {competition.federation.name if competition.federation else 'Independent'}\n"
        ', '.join(event.name for event in competition.events.all()[:5])

    )

    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.6,
        max_tokens=60
    )

    return response.choices[0].message.content.strip()

def get_local_qualifiers(start, end):
    local_qualifiers = []

    # Get competitions that are LOCAL (no Regional or Pro/Am tag)
    competitions = Competition.objects.exclude(
        tags__name__in=["Regional", "Pro/Am"]
    ).filter(
        comp_date__range=(start, end)
    ).distinct()

    for competition in competitions:
        athlete_entries = AthleteCompetition.objects.filter(
            competition=competition,
            total_points__gt=0,
            rank__isnull=False
        ).select_related('division', 'weight_class', 'athlete__user')

        # Group by division + weight_class
        grouped = defaultdict(list)
        for entry in athlete_entries:
            key = (entry.division.name if entry.division else "Open",
                   entry.weight_class.name if entry.weight_class else "Open")
            grouped[key].append(entry)

        for (division_name, weight_class_name), athletes in grouped.items():
            num_athletes = len(athletes)
            if num_athletes < 2:
                continue  # solo handled elsewhere

            # Sort by placing (rank)
            athletes_sorted = sorted(athletes, key=lambda a: a.rank or 9999)

            # Determine how many qualify
            if 2 <= num_athletes <= 4:
                max_place = 1
            elif 5 <= num_athletes <= 9:
                max_place = 2
            else:
                max_place = 3

            for athlete_entry in athletes_sorted:
                if athlete_entry.rank and athlete_entry.rank <= max_place:
                    local_qualifiers.append({
                        "user": athlete_entry.athlete.user,
                        "competition": competition,
                        "division": division_name,
                        "weight_class": weight_class_name,
                        "placing": athlete_entry.rank,
                        "competition_type": "Local",
                        "competition_date": competition.comp_date,
                        "reason": f"{athlete_entry.rank} place out of {num_athletes} athletes",
                    })

    return local_qualifiers

def get_regional_qualifiers(start, end):
    from collections import defaultdict
    from competitions.models import AthleteCompetition, Competition

    regional_qualifiers = []

    competitions = Competition.objects.filter(tags__name="Regional",
                                              comp_date__range=(start, end)
                                              ).distinct()

    for competition in competitions:
        athlete_entries = AthleteCompetition.objects.filter(
            competition=competition,
            total_points__gt=0,
            rank__isnull=False
        ).select_related('division', 'weight_class', 'athlete__user')

        grouped = defaultdict(list)
        for entry in athlete_entries:
            key = (
                entry.division.name if entry.division else "Open",
                entry.weight_class.name if entry.weight_class else "Open"
            )
            grouped[key].append(entry)

        for (division_name, weight_class_name), athletes in grouped.items():
            num_athletes = len(athletes)
            if num_athletes < 2:
                continue  # handled in solo rule

            athletes_sorted = sorted(athletes, key=lambda a: a.rank or 9999)

            # Determine how many qualify
            if 2 <= num_athletes <= 8:
                max_place = 3
            elif 9 <= num_athletes <= 11:
                max_place = 4
            else:
                max_place = 5

            for athlete_entry in athletes_sorted:
                if athlete_entry.rank <= max_place:
                    regional_qualifiers.append({
                        "user": athlete_entry.athlete.user,
                        "competition": competition,
                        "division": division_name,
                        "weight_class": weight_class_name,
                        "placing": athlete_entry.rank,
                        "competition_type": "Regional",
                        "competition_date": competition.comp_date,
                        "reason": f"{athlete_entry.rank} place out of {num_athletes} athletes",
                    })

    return regional_qualifiers

def get_pro_am_qualifiers(start, end):

    qualifiers = []

    competitions = Competition.objects.filter(
        tags__name="Pro/Am",
        comp_date__range=(start, end)
        ).distinct()


    for competition in competitions:
        athlete_entries = AthleteCompetition.objects.filter(
            competition=competition,
            total_points__gt=0,
            rank__isnull=False
        ).select_related('athlete__user', 'division', 'weight_class')

        # Filter only amateurs
        amateurs = [
            entry for entry in athlete_entries
            if getattr(entry.athlete.user, 'strongman_status', 'Amateur') == 'Amateur'
        ]

        amateurs_sorted = sorted(amateurs, key=lambda a: a.rank or 9999)
        top_5_amateurs = amateurs_sorted[:5]

        for athlete_entry in top_5_amateurs:
            division_name = athlete_entry.division.name if athlete_entry.division else "Open"
            weight_class_name = athlete_entry.weight_class.name if athlete_entry.weight_class else "Open"

            qualifiers.append({
                "user": athlete_entry.athlete.user,
                "competition": competition,
                "division": division_name,
                "weight_class": weight_class_name,
                "placing": athlete_entry.rank,
                "competition_type": "Pro/Am",
                "competition_date": competition.comp_date,
                "reason": f"Top 5 Amateur (Placed {athlete_entry.rank})",
            })

    return qualifiers

def create_or_update_qualifier(q):
    try:
        NationalsQualifier.objects.create(
            athlete=q["user"],
            competition=q["competition"],
            competition_type=q["competition_type"],
            competition_date=q["competition_date"],
            division=q["division"],
            weight_class=q["weight_class"],
            placing=q["placing"],
            qualification_reason=q["reason"]
        )
    except IntegrityError:
        pass