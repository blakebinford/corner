import stripe
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, HttpResponseBadRequest
from competitions.models import AthleteCompetition
import logging

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY

@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    logger.debug("Stripe webhook received – signature header: %r", sig_header)
    logger.debug("Payload bytes: %d", len(payload))
    print(">>> WEBHOOK HIT!", request.method, request.path)
    print("Signature header:", request.META.get("HTTP_STRIPE_SIGNATURE"))
    print("Payload (first 200 chars):", request.body[:200])
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        logger.warning("Invalid payload")
        return HttpResponseBadRequest("Invalid payload")
    except stripe.error.SignatureVerificationError:
        logger.warning("Invalid signature")
        return HttpResponseBadRequest("Invalid signature")

    # Handle the checkout.session.completed event
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        metadata = session.get("metadata", {})
        reg_id = metadata.get("athlete_competition_id")
        print(f"➡️  checkout.session.completed, metadata={metadata}")
        if reg_id:
            try:
                reg = AthleteCompetition.objects.get(pk=reg_id)
                if reg.payment_status != "paid":
                    reg.payment_status = "paid"
                    reg.registration_status = "complete"
                    reg.signed_up = True
                    reg.save()
            except AthleteCompetition.DoesNotExist:
                pass  # log this if you like

    return HttpResponse(status=200)
