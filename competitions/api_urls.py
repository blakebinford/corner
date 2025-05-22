# competitions/api_urls.py
from django.urls import path
from .views import CompetitionListView as APICompetitionListView
from .views import APICompetitionDetailView, CompetitionByStatusView, APIAthleteCompetitionDetailView

urlpatterns = [
    path('competitions/', APICompetitionListView.as_view(), name='competition-list'),
    path('competitions/<int:id>/', APICompetitionDetailView.as_view(), name='competition-detail'),
    path('competitions/status/<str:status>/', CompetitionByStatusView.as_view(), name='competition-by-status'),
    path('athlete-competition/<int:id>/', APIAthleteCompetitionDetailView.as_view(), name='athlete-competition-detail'),
]