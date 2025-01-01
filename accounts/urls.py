from django.urls import path, include, reverse_lazy
from django.contrib.auth import views as auth_views
from . import views

app_name = 'accounts'

urlpatterns = [
    path('signup/', views.SignUpView.as_view(), name='signup'),
    path('profile/update/', views.update_profile, name='profile_update'),
    path('update_athlete_profile/', views.AthleteProfile, name='update_athlete_profile'),
    path('update_organizer_profile/', views.OrganizerProfileUpdateView.as_view(), name='update_organizer_profile'),
    path('', include('django.contrib.auth.urls')),
    path('logout/', auth_views.LogoutView.as_view(next_page='home'), name='logout'),
    path('get_weight_classes/', views.get_weight_classes, name='get_weight_classes'),
    path('password_reset/', auth_views.PasswordResetView.as_view(
        template_name='registration/password_reset_form.html',
        email_template_name='registration/password_reset_email.html',
        subject_template_name='registration/password_reset_subject.txt',
        success_url=reverse_lazy('accounts:password_reset_done')  # Use reverse_lazy here
    ), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='registration/password_reset_done.html'
    ), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='registration/password_reset_confirm.html',
        success_url=reverse_lazy('accounts:password_reset_complete')  # Use reverse_lazy here
    ), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(
        template_name='registration/password_reset_complete.html'
    ), name='password_reset_complete'),
]
