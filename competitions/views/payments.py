import stripe
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse

from competitions.models import Competition, AthleteCompetition
from accounts.models import OrganizerProfile

stripe.api_key = settings.STRIPE_SECRET_KEY


@login_required
def payment_page(request, competition_id, athlete_competition_id):
    competition = get_object_or_404(Competition, pk=competition_id)
    registration = get_object_or_404(
        AthleteCompetition,
        pk=athlete_competition_id,
        competition=competition,
        athlete__user=request.user
    )
    return render(request, "competitions/payments/checkout.html", {
        "competition": competition,
        "registration": registration,
        "stripe_pub_key": settings.STRIPE_PUBLISHABLE_KEY,
    })


@login_required
def start_checkout(request, competition_id, athlete_competition_id):
    """
    Creates a single, fully‐configured Stripe Checkout Session and redirects there.
    """
    competition = get_object_or_404(Competition, pk=competition_id)
    registration = get_object_or_404(
        AthleteCompetition,
        pk=athlete_competition_id,
        competition=competition,
        athlete__user=request.user
    )

    # only let the athlete pay their own registration
    if registration.athlete.user != request.user:
        return HttpResponseForbidden("You can only pay for your own registration.")

    # fetch the organizer's Stripe account
    try:
        organizer_profile = competition.organizer.organizer_profile
    except OrganizerProfile.DoesNotExist:
        return HttpResponseForbidden("Organizer has not connected a Stripe account.")

    # compute amount (in cents)
    entry_fee_cents = int(competition.signup_price * Decimal(100))
    platform_fee_cents = int(entry_fee_cents * Decimal("0.10"))

    # build our success / cancel URLs, with Stripe's session_id placeholder
    base_success = request.build_absolute_uri(
        reverse("competitions:checkout_success", args=[competition.id, registration.id])
    )
    success_url = f"{base_success}?session_id={{CHECKOUT_SESSION_ID}}"

    cancel_url = request.build_absolute_uri(
        reverse("competitions:checkout_cancel", args=[competition.id, registration.id])
    )

    # --- START NEW CODE ---
    athlete_name = registration.athlete.user.get_full_name()
    competition_name = competition.name
    # --- END NEW CODE ---

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[
            {
                "price_data": {
                    "currency": "usd",
                    "unit_amount": entry_fee_cents,
                    "product_data": {
                        "name": f"{competition.name} Entry Fee"
                    },
                },
                "quantity": 1,
            },
            {
                "price_data": {
                    "currency": "usd",
                    "unit_amount": platform_fee_cents,
                    "product_data": {
                        "name": "Atlas Service Fee"
                    },
                },
                "quantity": 1,
            },
        ],
        mode="payment",
        success_url=success_url,
        cancel_url=cancel_url,
        payment_intent_data={
            "application_fee_amount": platform_fee_cents,  # only this goes to your platform
            "transfer_data": {
                "destination": organizer_profile.stripe_account_id,
            },
            "metadata": {
                "competition_id": str(competition.id),
                "competition_name": competition.name,
                "athlete_competition_id": str(registration.id),
                "athlete_name": athlete_name,
            },
        },
        metadata={
            "competition_id": str(competition.id),
            "competition_name": competition.name,
            "athlete_competition_id": str(registration.id),
            "athlete_name": athlete_name,
        },
    )

    return redirect(session.url)


@login_required
def checkout_success(request, competition_id, athlete_competition_id):
    session_id = request.GET.get("session_id")
    if not session_id:
        return render(request, "competitions/payments/error.html", {
            "message": "No session_id provided."
        }, status=400)

    session = stripe.checkout.Session.retrieve(session_id)
    if session.payment_status != "paid":
        return render(request, "competitions/payments/error.html", {
            "message": "Payment not completed."
        }, status=402)

    registration = get_object_or_404(
        AthleteCompetition,
        pk=athlete_competition_id,
        competition__pk=competition_id,
        athlete__user=request.user
    )

    # update only once
    if registration.payment_status != "paid":
        registration.payment_status = "paid"
        registration.registration_status = "complete"
        registration.signed_up = True
        registration.save()

    return render(request, "competitions/payments/success.html", {
        "competition": registration.competition,
        "registration": registration,
    })


@login_required
def checkout_cancel(request, competition_id, athlete_competition_id):
    registration = get_object_or_404(
        AthleteCompetition,
        pk=athlete_competition_id,
        competition__pk=competition_id,
        athlete__user=request.user
    )
    registration.payment_status = "cancelled"
    registration.save()

    return render(request, "competitions/payments/cancel.html", {
        "competition": registration.competition,
        "registration": registration,
    })
