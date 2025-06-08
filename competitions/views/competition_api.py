from django.shortcuts import get_object_or_404, render
from rest_framework import generics, status
from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import api_view
from rest_framework.views import APIView
from rest_framework.response import Response
from competitions.models import Competition, AthleteCompetition
from competitions.serializers import CompetitionSerializer, AthleteCompetitionSerializer
from rest_framework.permissions import IsAuthenticated, BasePermission
from drf_spectacular.utils import extend_schema, OpenApiParameter
class APICompetitionListView(generics.ListAPIView):
    queryset = Competition.objects.all()
    serializer_class = CompetitionSerializer

class IsReadOnlyUser(BasePermission):
    def has_permission(self, request, view):
        return request.user.username == 'vmix_user' or 'blake' and request.method in ['GET', 'HEAD', 'OPTIONS']


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
        OpenApiParameter(name='name', description='Full name of the athlete (e.g. John Smith)', required=True, type=str),
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