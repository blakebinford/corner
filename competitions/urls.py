from django.urls import path, re_path
from . import views
from .consumers import ScoreUpdateConsumer
from .views import EventUpdateView, SponsorEditView, OrganizerCompetitionsView, ManageCompetitionView, AthleteListView

app_name = 'competitions'

urlpatterns = [
    path('', views.CompetitionListView.as_view(), name='competition_list'),
    path('<int:pk>/', views.CompetitionDetailView.as_view(), name='competition_detail'),
    path('create/', views.CompetitionCreateView.as_view(), name='competition_create'),
    path('<int:pk>/update/', views.CompetitionUpdateView.as_view(), name='competition_update'),
    path('<int:pk>/delete/', views.CompetitionDeleteView.as_view(), name='competition_delete'),

    path('get_weight_classes/', views.get_weight_classes, name='get_weight_classes'),

    # Event URLs
    path('event/create/<int:competition_pk>/', views.EventCreateView.as_view(), name='event_create'),
    path('event/<int:pk>/update/', EventUpdateView.as_view(), name='event_update'),
    path('event/<int:pk>/delete/', views.EventDeleteView.as_view(), name='event_delete'),
    path('ws/competitions/<int:competition_pk>/', ScoreUpdateConsumer.as_asgi()),
    path('<int:pk>/score/', views.CompetitionScoreView.as_view(), name='competition_score'),
    path('<int:competition_id>/update_score/<int:athlete_competition_id>/<int:event_order_id>/', views.update_score, name='update_score'),
    path('<int:competition_id>/update_multiple_scores/', views.update_multiple_scores, name='update_multiple_scores'),
    path('<int:pk>/scorecard/', views.CompetitionScorecardView.as_view(), name='competition_scorecard'),
    path('<int:competition_pk>/athlete/<int:athletecompetition_pk>/event/<int:eventorder_pk>/score/', views.update_score, name='update_score'),
    path('<int:competition_id>/commentator_compcard/', views.commentator_comp_card, name='commentator_comp_card'),
    path('<int:competition_pk>/upload_sponsor_logos/', views.SponsorLogoUploadView.as_view(), name='sponsor_logo_upload'),
    path('<int:competition_pk>/edit_sponsor_logos/', SponsorEditView.as_view(), name='edit_sponsor_logos'),
    path('organizer/competitions/', OrganizerCompetitionsView.as_view(), name='organizer_competitions'),
    path('competition/<int:competition_pk>/manage/', ManageCompetitionView.as_view(), name='manage_competition'),
    path('competition/<int:competition_pk>/participants/', AthleteListView.as_view(), name='athlete_list'),
    path('<int:competition_pk>/send_email/', views.send_email_to_athletes, name='send_email'),

    # AthleteCompetition URLs
    path('<int:competition_pk>/register/', views.AthleteCompetitionCreateView.as_view(), name='athletecompetition_create'),
    path('athletecompetition/<int:pk>/update/', views.AthleteCompetitionUpdateView.as_view(), name='athletecompetition_update'),
    path('athletecompetition/<int:pk>/delete/', views.AthleteCompetitionDeleteView.as_view(), name='athletecompetition_delete'),
    path('athlete/<int:athlete_id>/', views.athlete_profile, name='athlete_profile'),
]