import boto3
from openai import OpenAI

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

