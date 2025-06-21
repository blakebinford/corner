from datetime import date

from django.http import HttpResponseNotFound
from django.shortcuts import get_object_or_404, render, redirect, reverse
from rest_framework import generics, status
from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import api_view, permission_classes
from rest_framework.views import APIView
from rest_framework.response import Response
from competitions.models import Competition, AthleteCompetition, CompetitionRunOrder, Event
from accounts.models import AthleteProfile, User
from competitions.serializers import CompetitionSerializer, AthleteCompetitionSerializer
from rest_framework.permissions import IsAuthenticated, BasePermission, AllowAny
from drf_spectacular.utils import extend_schema, OpenApiParameter

from competitions.utils import generate_presigned_url


@api_view(["GET"])
@permission_classes([AllowAny])
def serve_profile_picture(request, user_id):
    user = get_object_or_404(User, pk=user_id)

    if user.profile_picture:
        url = generate_presigned_url(user.profile_picture.name)
        return redirect(url)

    return HttpResponseNotFound("No profile picture found.")


class APICompetitionListView(generics.ListAPIView):
    queryset = Competition.objects.all()
    serializer_class = CompetitionSerializer


class IsReadOnlyUser(BasePermission):
    def has_permission(self, request, view):
        return request.user.username == 'vmix_user' or 'blake' and request.method in ['GET', 'HEAD', 'OPTIONS']


def _format_height_inches(h):
    """
    Convert an integer height in inches to 'XFT YIN' format.
    """
    try:
        feet = h // 12
        inches = h % 12
        return f"{feet}FT {inches}IN"
    except Exception:
        return ""


def _calculate_age(dob):
    """
    Calculate age in years from a date_of_birth.
    """
    if not dob:
        return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


# GET /api/competition/<id>/
@extend_schema(
    summary="Get competition details and full athlete list",
    description="Returns core metadata and structure for a given competition, including athlete list and event info.",
    parameters=[
        OpenApiParameter(name="pk", description="Competition ID", required=True, type=int),
    ],
    responses={200: CompetitionSerializer}
)
class APICompetitionDetailView(generics.RetrieveAPIView):
    queryset = Competition.objects.all()
    serializer_class = CompetitionSerializer
    lookup_field = 'id'
    permission_classes = [IsAuthenticated, IsReadOnlyUser]


class APIAthleteCompetitionDetailView(generics.RetrieveAPIView):
    queryset = AthleteCompetition.objects.all()
    serializer_class = AthleteCompetitionSerializer
    lookup_field = 'id'

    def get_queryset(self):
        status = self.kwargs['status']
        return Competition.objects.filter(status=status)


@extend_schema(
    summary="List athletes in a competition",
    description="Returns all athletes registered for a specific competition, including full athlete profile, division, weight class, and results.",
    parameters=[
        OpenApiParameter(name="pk", description="Competition ID", required=True, type=int),
    ],
    responses={200: AthleteCompetitionSerializer(many=True)},
    tags=["Competition"],
)
class CompetitionAthletesAPI(APIView):
    permission_classes = [IsAuthenticated, IsReadOnlyUser]

    def get(self, request, pk):
        athletes = AthleteCompetition.objects.filter(competition_id=pk)
        serializer = AthleteCompetitionSerializer(athletes, many=True)
        return Response(serializer.data)


@extend_schema(
    parameters=[
        OpenApiParameter(name='name', description='Full name of the athlete (e.g. John Smith)', required=True,
                         type=str),
    ],
    responses={200: AthleteCompetitionSerializer},
    methods=["GET"],
    description="Retrieve a single athlete's competition entry by full name and competition slug."
)
@api_view(['GET'])
def athlete_by_name(request, comp_id):
    """
    Lookup athlete by name within a competition using the competition ID.
    Usage: /api/competition/42/athlete-by-name/?name=Matthew-Johnson
    """
    name = request.GET.get('name')
    if not name:
        return Response({"error": "Missing 'name' parameter"}, status=status.HTTP_400_BAD_REQUEST)

    competition = get_object_or_404(Competition, pk=comp_id)

    split_name = name.replace("-", " ").split()
    if len(split_name) < 2:
        return Response({"error": "Please provide a full name (first and last)."}, status=400)

    first_name, last_name = split_name[0], split_name[-1]

    matching = AthleteCompetition.objects.filter(
        competition=competition,
        athlete__user__first_name__iexact=first_name,
        athlete__user__last_name__iexact=last_name
    ).first()

    if not matching:
        return Response({"error": "Athlete not found in this competition"}, status=404)

    serializer = AthleteCompetitionSerializer(matching)
    return Response(serializer.data)


def api_guide(request):
    return render(request, 'competitions/api_guide.html')


@extend_schema(
    summary="vMix: Top-N Leaderboard",
    parameters=[
        # competitionID, weightClassID, listSize in query string
    ],
    responses={200: dict(many=True)},
    methods=["GET"],
    tags=["vMix"],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def leaderboard(request):
    comp_id = request.GET.get("competitionID")
    weight_id = request.GET.get("weightClassID")
    try:
        list_size = int(request.GET.get("listSize", 10))
    except ValueError:
        list_size = 10

    # Top N by total_points in that class
    regs = (
        AthleteCompetition.objects
        .filter(competition_id=comp_id, weight_class_id=weight_id)
        .order_by("-total_points")[:list_size]
    )  # :contentReference[oaicite:0]{index=0}

    data = []
    for idx, ac in enumerate(regs, start=1):
        div = ac.division  # Division instance
        wc = ac.weight_class
        data.append({
            "className": f"{div.name} – {wc.name}{wc.weight_d}",
            "position": idx,
            "athleteName": ac.athlete.user.get_full_name().upper(),
            "points": ac.total_points,
        })

    return Response(data)


@api_view(["GET"])
@permission_classes([AllowAny])
def current_competitors(request):
    comp_id = request.GET.get("competitionID")
    event_id = request.GET.get("eventID")

    competition = get_object_or_404(Competition, pk=comp_id)

    if event_id:
        event = get_object_or_404(Event, pk=event_id, competition=competition)
    else:
        event = competition.current_event

    if not event:
        return Response([])

    ros = (
        CompetitionRunOrder.objects
        .filter(competition=competition, event=event, status="current")
        .order_by("lane_number", "order")
    )

    current_by_lane = {}
    for ro in ros:
        lane = ro.lane_number or 1
        if lane not in current_by_lane:
            current_by_lane[lane] = ro

    data = []
    for lane, ro in current_by_lane.items():
        ac = ro.athlete_competition
        prof = ac.athlete
        user = prof.user

        data.append({
            "eventID": event.pk,
            "eventName": event.name,
            "lane": lane,
            "name": user.get_full_name().upper(),
            "nickname": prof.nickname,
            "instagram": getattr(user, "instagram_name", ""),
            "gender": prof.gender,
            "height": _format_height_inches(prof.height),
            "weight": str(prof.weight) if prof.weight else "",
            "age": _calculate_age(prof.date_of_birth),
            "division": ac.division.name if ac.division else "",
            "weight_class": (
                f"u{ac.weight_class.name}" if ac.weight_class.weight_d == "u"
                else f"{ac.weight_class.name}+" if ac.weight_class.weight_d == "+"
                else ac.weight_class.name
            ) if ac.weight_class else "",
            "street": prof.street_number,
            "city": prof.city,
            "state": prof.state,
            "zip_code": prof.zip_code,
            "home_gym": prof.home_gym,
            "team": prof.team_name,
            "coach": prof.coach,
            "bio": prof.bio,
            "imageUrl": request.build_absolute_uri(
                reverse("serve_profile_picture", args=[user.id])
            ) if user.profile_picture else "",

        })

    return Response(data)


@api_view(["GET"])
@permission_classes([AllowAny])
def up_next_competitors(request):
    comp_id = request.GET.get("competitionID")
    event_id = request.GET.get("eventID")

    competition = get_object_or_404(Competition, pk=comp_id)

    if event_id:
        event = get_object_or_404(Event, pk=event_id, competition=competition)
    else:
        event = competition.current_event

    if not event:
        return Response([])

    pending_qs = (
        CompetitionRunOrder.objects
        .filter(competition=competition, event=event, status="pending")
        .order_by("lane_number", "order")
    )

    next_by_lane = {}
    for ro in pending_qs:
        lane = ro.lane_number or 1
        if lane not in next_by_lane:
            next_by_lane[lane] = ro

    data = []
    for lane, ro in next_by_lane.items():
        ac = ro.athlete_competition
        prof = ac.athlete
        user = prof.user
        data.append({
            "eventID": event.pk,
            "eventName": event.name,
            "lane": ro.lane_number or 1,
            "name": user.get_full_name().upper(),
            "nickname": prof.nickname,
            "instagram": getattr(user, "instagram_name", ""),
            "gender": prof.gender,
            "height": _format_height_inches(prof.height),
            "weight": str(prof.weight) if prof.weight else "",
            "age": _calculate_age(prof.date_of_birth),
            "division": ac.division.name if ac.division else "",
            "weight_class": ac.weight_class.name if ac.weight_class else "",
            "street": prof.street_number,
            "city": prof.city,
            "state": prof.state,
            "zip_code": prof.zip_code,
            "home_gym": prof.home_gym,
            "team": prof.team_name,
            "coach": prof.coach,
            "bio": prof.bio,
            "imageUrl": request.build_absolute_uri(
                reverse("serve_profile_picture", args=[user.id])
            ) if user.profile_picture else "",

        })

    return Response(data)


@api_view(["GET"])
@permission_classes([AllowAny])
def current_event(request):
    comp_id = request.GET.get("competitionID")
    competition = get_object_or_404(Competition, pk=comp_id)
    event = competition.current_event

    if not event:
        return Response([])

    # Get first current lifter in the run order
    current_ro = (
        CompetitionRunOrder.objects
        .filter(competition=competition, event=event, status="current")
        .order_by("lane_number", "order")
        .first()
    )

    if current_ro:
        ac = current_ro.athlete_competition
        division_name = ac.division.name if ac.division else ""
        weight_class_name = ac.weight_class.name if ac.weight_class else ""
        gender = ac.athlete.gender if ac.athlete and ac.athlete.gender else ""
        event_class = f"{division_name} - {weight_class_name}".strip(" -")
    else:
        event_class = ""
        gender = ""

    return Response([{
        "event_name": event.name,
        "event_class": event_class,
        "gender": gender
    }])


@api_view(["GET"])
@permission_classes([AllowAny])
def competition_events(request):
    """
    ?competitionID=42
    Returns all events in that competition:
      [{ id: 7, name: "18\" Deadlift" }, …]
    """
    comp_id = request.GET.get("competitionID")
    if not comp_id:
        return Response([], status=400)

    try:
        comp = Competition.objects.get(pk=comp_id)
    except Competition.DoesNotExist:
        return Response([], status=404)

    evs = comp.events.all().order_by("order")
    data = [{"id": e.pk, "name": e.name} for e in evs]
    return Response(data)


@api_view(["GET"])
@permission_classes([AllowAny])
def competition_weight_classes(request):
    """
    ?competitionID=42
    Returns all WeightClass instances attached to that Competition:
      [{ id: 5, name: "231.5 – Middleweight" }, …]
    """
    comp_id = request.GET.get("competitionID")
    if not comp_id:
        return Response([], status=400)

    competition = get_object_or_404(Competition, pk=comp_id)

    # Use the related_name on WeightClass.competition
    wcs = competition.weight_classes.select_related("division").all()

    data = [
        {"id": wc.pk, "name": str(wc)}
        for wc in wcs
    ]
    return Response(data)
