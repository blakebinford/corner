# competitions/api_urls.py
from django.urls import path
from .views import CompetitionListView as APICompetitionListView, CompetitionAthletesAPI, api_guide
from .views import APICompetitionDetailView, APIAthleteCompetitionDetailView, athlete_by_name
from competitions.views.competition_api import (
    leaderboard,
    current_competitors,
    up_next_competitors,
    current_event,
    competition_events,
    competition_weight_classes,
)

urlpatterns = [
    path('competition/events',              competition_events,          name='api_competition_events'),
    path('competition/weight-classes',      competition_weight_classes,  name='api_competition_wcs'),
    path('competition/', APICompetitionListView.as_view(), name='competition-list'),
    path('competition/<int:id>/', APICompetitionDetailView.as_view(), name='competition-detail'),
    path('competition/<int:pk>/athletes/', CompetitionAthletesAPI.as_view(), name='competition-athletes'),
    path('competition/<int:comp_id>/athlete-by-name/', athlete_by_name),
    path("api-guide/", api_guide, name="api_guide"),
    path('competition/leaderboard',           leaderboard,            name='api_leaderboard'),
    path('competition/current-competitors',   current_competitors,    name='api_current_competitors'),
    path('competition/up-next-competitors',   up_next_competitors,    name='api_up_next_competitors'),
    path('competition/current-event',         current_event,          name='api_current_event'),
]