import boto3
from django.conf import settings

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

