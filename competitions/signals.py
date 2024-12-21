from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import AthleteCompetition, Competition, Result
from competitions.views import calculate_points_and_rankings

@receiver(post_save, sender=AthleteCompetition)
def update_competition_status(sender, instance, created, **kwargs):
    """
    Updates the Competition status to 'full' if the number of registered athletes
    reaches the capacity.
    """
    if created:
        competition = instance.competition
        # Use the related_name 'athlete_competitions' to count registered athletes
        if competition.athlete_competitions.count() >= competition.capacity:
            competition.status = 'full'
            competition.save()

@receiver(post_save, sender=Result)
def update_score_and_rankings(sender, instance, created, **kwargs):
    """
    Updates the scores and rankings whenever a new Result is saved.
    """
    if created:
        calculate_points_and_rankings(instance.athlete_competition.competition.pk, instance.event_order.pk)
