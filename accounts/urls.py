from django.urls import path, include
from django.contrib.auth import views as auth_views
from . import views

app_name = 'accounts'

urlpatterns = [
    path('signup/', views.SignUpView.as_view(), name='signup'),
    path('profile/update/', views.update_profile, name='profile_update'),
    path('profile/update/', views.update_profile, name='profile_update'),
    path('update_athlete_profile/', views.AthleteProfile, name='update_athlete_profile'),
    path('update_organizer_profile/', views.OrganizerProfileUpdateView.as_view(), name='update_organizer_profile'),
    path('', include('django.contrib.auth.urls')),
    path('logout/', auth_views.LogoutView.as_view(next_page='home'), name='logout'),
]
