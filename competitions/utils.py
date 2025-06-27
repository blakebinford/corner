import boto3
from django.conf import settings
from django.core.exceptions import PermissionDenied

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

def competition_permission_required(permission_type):
    def decorator(view_func):
        def _wrapped_view(request, *args, **kwargs):
            competition = get_object_or_404(Competition, pk=kwargs['competition_pk'])

            if permission_type == 'full' and not competition.has_full_access(request.user):
                raise PermissionDenied
            elif permission_type == 'any' and not competition.has_any_access(request.user):
                raise PermissionDenied

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator