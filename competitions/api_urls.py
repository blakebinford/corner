# competitions/api_urls.py
from django.urls import path
from .views import CompetitionListView as APICompetitionListView, CompetitionAthletesAPI, api_guide
from .views import APICompetitionDetailView, APIAthleteCompetitionDetailView, athlete_by_name

urlpatterns = [
    path('competitions/', APICompetitionListView.as_view(), name='competition-list'),
    path('competitions/<int:id>/', APICompetitionDetailView.as_view(), name='competition-detail'),
    path('competitions/<int:pk>/athletes/', CompetitionAthletesAPI.as_view(), name='competition-athletes'),
    path('competition/<int:comp_id>/athlete-by-name/', athlete_by_name),
    path("api-guide/", api_guide, name="api_guide"),
]