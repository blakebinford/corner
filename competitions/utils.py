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

