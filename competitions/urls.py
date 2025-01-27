from django.urls import path, re_path
from . import views
from .consumers import ScoreUpdateConsumer
from .views import SponsorEditView, OrganizerCompetitionsView, ManageCompetitionView, AthleteListView, \
    CompleteCompetitionView, ArchivedCompetitionListView, EditWeightClassesView, AthleteCheckInView, \
    toggle_publish_status, AddAthleteManuallyView, CreateAthleteProfileView, AssignWeightClassesView, \
    CustomDivisionCreateView, CustomWeightClassCreateView

app_name = 'competitions'

urlpatterns = [
    path('', views.CompetitionListView.as_view(), name='competition_list'),
    path('<int:pk>/', views.CompetitionDetailView.as_view(), name='competition_detail'),
    path('create/', views.CompetitionCreateView.as_view(), name='competition_create'),
    path('<int:pk>/update/', views.CompetitionUpdateView.as_view(), name='competition_update'),
    path('<int:pk>/delete/', views.CompetitionDeleteView.as_view(), name='competition_delete'),

    path('get_weight_classes/', views.get_weight_classes, name='get_weight_classes'),
    path(
        "competitions/<int:pk>/assign-weight-classes/",
        AssignWeightClassesView.as_view(),
        name="assign_weight_classes",
    ),
    path('division/<int:division_id>/weight-classes/', views.get_division_weight_classes, name='division_weight_classes'),

    # Event URLs
    path('competition/<int:competition_pk>/event/create/', views.create_event, name='create_event'),
    path('event/<int:event_pk>/implements/assign/', views.assign_implements, name='assign_implements'),
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
    path(
        'competition/<int:competition_pk>/overlay-image/<int:user_pk>/',
        views.competition_overlay_image,
        name='competition_overlay_image',
    ),
    path('competitions/<int:competition_pk>/edit_weight_classes/', EditWeightClassesView.as_view(), name='edit_weight_classes'),
    path('competitions/archived/', ArchivedCompetitionListView.as_view(), name='archived_competition_list'),
    path('competition/<int:competition_pk>/overlay/<int:user_pk>/',
         views.competition_overlay, name='competition_overlay'),
    path('<int:competition_pk>/events/', views.event_list, name='event_list'),
    path('<int:competition_pk>/events/<int:eventorder_pk>/scores/', views.event_scores, name='event_scores'),
    path('competition/<int:competition_pk>/complete/', CompleteCompetitionView.as_view(), name='complete_competition'),
    path('competitions/<int:competition_pk>/checkin/', AthleteCheckInView.as_view(), name='checkin_athletes'),
    path('competitions/<int:pk>/toggle_publish/', toggle_publish_status, name='toggle_publish_status'),
    path('<int:competition_pk>/toggle_email_notifications/', views.toggle_email_notifications, name='toggle_email_notifications'),
    path('competitions/<int:competition_pk>/download_athlete_table/', views.download_athlete_table, name='download_athlete_table'),
    path('competitions/<int:competition_pk>/add_athlete/', AddAthleteManuallyView.as_view(), name='add_athlete'),
    path('competitions/<int:competition_pk>/create_athlete_profile/', CreateAthleteProfileView.as_view(),
         name='create_athlete_profile'),
    path(
        'competitions/<int:competition_pk>/combine_weight_classes/',
        views.CombineWeightClassesView.as_view(),
        name='combine_weight_classes'
    ),
    path('event/<int:event_pk>/edit/', views.update_event, name='update_event'),
    path('competitions/<int:competition_pk>/custom-division/add/', CustomDivisionCreateView.as_view(), name='add_custom_division'),
    path('competitions/<int:competition_pk>/custom-weight-class/add/', CustomWeightClassCreateView.as_view(), name='add_custom_weight_class'),

    # AthleteCompetition URLs
    path('<int:competition_pk>/register/', views.AthleteCompetitionCreateView.as_view(), name='athletecompetition_create'),
    path('athletecompetition/<int:pk>/edit/', views.AthleteCompetitionUpdateView.as_view(), name='athletecompetition_update'),

    path('athletecompetition/<int:pk>/delete/', views.AthleteCompetitionDeleteView.as_view(), name='athletecompetition_delete'),
    path('athlete/<int:athlete_id>/', views.athlete_profile, name='athlete_profile'),

]