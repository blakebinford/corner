import json

import stripe
import os
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET

from accounts.models import OrganizerProfile
# use the same API version as the quickstart
stripe.api_key = settings.STRIPE_SECRET_KEY
stripe.api_version = '2023-10-16'


def onboarding_page(request, account_id=None, action=None):
    """
    Serves the single-page onboarding React-like UI.
    It’ll live at:
      /stripe/onboarding/
      /stripe/return/<account_id>/
      /stripe/refresh/<account_id>/
    The JS detects the path and shows the right state.
    """
    return render(request, 'competitions/stripe_onboarding.html')

# competitions/views/stripe_connect.py


stripe.api_key = settings.STRIPE_SECRET_KEY

@login_required
@require_GET
def connect_stripe(request):
    profile, created = OrganizerProfile.objects.get_or_create(user=request.user)
    # 1. Create account if needed
    if not profile.stripe_account_id:
        acct = stripe.Account.create(
            type="express",
            country="US",
            email=request.user.email,
        )
        profile.stripe_account_id = acct.id
        profile.save()

    # 2. Create onboarding link
    account_link = stripe.AccountLink.create(
        account=profile.stripe_account_id,
        refresh_url=request.build_absolute_uri(reverse("competitions:connect")),
        return_url=request.build_absolute_uri(reverse("competitions:onboard_complete")),
        type="account_onboarding",
    )
    # 3. Redirect user into Stripe onboarding
    return redirect(account_link.url)


@csrf_exempt
@require_POST
def create_account_link(request):
    """
    POST /stripe/account_link/ { account: acctId }
      → { "url": onboardingUrl }
    """
    data = json.loads(request.body)
    acct_id = data.get('account')
    link = stripe.AccountLink.create(
        account=acct_id,
        return_url=request.build_absolute_uri(
            f"/stripe/return/{acct_id}/"
        ),
        refresh_url=request.build_absolute_uri(
            f"/stripe/refresh/{acct_id}/"
        ),
        type='account_onboarding'
    )
    return JsonResponse({'url': link.url})

@login_required
def onboard_complete(request):
    """
    After the user finishes Stripe-hosted onboarding,
    we land here (you could inspect account requirements
    via stripe.Account.retrieve if you like).
    """
    profile = get_object_or_404(OrganizerProfile, user=request.user)
    acct = stripe.Account.retrieve(profile.stripe_account_id)
    return render(request, "competitions/onboard_complete.html")

@login_required
def connect_stripe(request):
    # 1) Create a Stripe Express account (or get existing)
    profile, _ = OrganizerProfile.objects.get_or_create(user=request.user)
    if not profile.stripe_account_id:
        acct = stripe.Account.create(type="express", country="US", email=request.user.email)
        profile.stripe_account_id = acct.id
        profile.save()

    # 2) Generate an account-link for onboarding
    link = stripe.AccountLink.create(
        account=profile.stripe_account_id,
        refresh_url=request.build_absolute_uri(reverse("competitions:connect")),
        return_url =request.build_absolute_uri(reverse("competitions:onboard_complete")),
        type="account_onboarding",
    )
    return redirect(link.url)

@login_required
def onboard_complete(request):
    profile = get_object_or_404(OrganizerProfile, user=request.user)
    acct = stripe.Account.retrieve(profile.stripe_account_id)
    if acct.charges_enabled:
        messages.success(request, "Your Stripe account is ready to accept payments!")
    else:
        messages.warning(request, "Your Stripe onboarding is still incomplete.")
    return redirect("competitions:organizer_competitions")

from django.contrib import messages
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect
import stripe

@login_required
def login_stripe_express(request):
    user = request.user
    try:
        organizer = user.organizer_profile
    except AttributeError:
        return HttpResponseBadRequest("Organizer profile required.")

    if not organizer.stripe_account_id:
        messages.error(request, "You must first connect your Stripe account.")
        return redirect('update_organizer_profile')  # or wherever your Stripe onboarding starts

    try:
        acct_id = str(organizer.stripe_account_id)
        link = stripe.Account.create_login_link(acct_id)
        return redirect(link.url)
    except stripe.error.InvalidRequestError as e:
        messages.error(request, f"Stripe error: {e.user_message or str(e)}")
    except Exception as e:
        messages.error(request, f"Unexpected error: {str(e)}")

    return redirect('dashboard')  # or fallback route
