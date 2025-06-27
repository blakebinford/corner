from django.urls import path, include, reverse_lazy
from django.contrib.auth import views as auth_views
from django.contrib import messages
from django.views.generic import TemplateView

from . import views

app_name = 'accounts'

class CustomPasswordResetView(auth_views.PasswordResetView):
    def form_valid(self, form):
        messages.success(self.request, "If an account with the provided email exists, a password reset link has been sent. Please check your inbox.")
        return super().form_valid(form)

urlpatterns = [
    path('signup/', views.SignUpView.as_view(), name='signup'),
    path('profile/update/', views.update_profile, name='profile_update'),
    path('update_athlete_profile/', views.update_profile, name='update_athlete_profile'),  # ✅ Fixed
    path('update_organizer_profile/', views.OrganizerProfileUpdateView.as_view(), name='update_organizer_profile'),
    path('', include('django.contrib.auth.urls')),  # Consider removing if not needed
    path('logout/', auth_views.LogoutView.as_view(next_page=reverse_lazy('home')), name='logout'),  # ✅ Ensures 'home' exists
    path('get_weight_classes/', views.get_weight_classes, name='get_weight_classes'),
    path('password_reset/', CustomPasswordResetView.as_view(  # ✅ Using CustomPasswordResetView
        template_name='registration/password_reset_form.html',
        email_template_name='registration/password_reset_email.html',
        subject_template_name='registration/password_reset_subject.txt',
        success_url=reverse_lazy('accounts:password_reset_done'),
    ), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='registration/password_reset_done.html'
    ), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='registration/password_reset_confirm.html',
        success_url=reverse_lazy('accounts:password_reset_complete')
    ), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(
        template_name='registration/password_reset_complete.html'
    ), name='password_reset_complete'),
    path('privacy/', TemplateView.as_view(template_name='registration/legal/privacy.html'), name='privacy_policy'),
    path('terms/', TemplateView.as_view(template_name='registration/legal/terms.html'), name='terms_of_service'),
    path('cookies/', TemplateView.as_view(template_name='registration/legal/cookies.html'), name='cookie_policy'),
]
