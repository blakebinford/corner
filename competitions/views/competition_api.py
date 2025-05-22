from rest_framework import generics
from competitions.models import Competition, AthleteCompetition
from competitions.serializers import CompetitionSerializer, AthleteCompetitionSerializer
from rest_framework.permissions import IsAuthenticated, BasePermission

class APICompetitionListView(generics.ListAPIView):
    queryset = Competition.objects.all()
    serializer_class = CompetitionSerializer

class IsReadOnlyUser(BasePermission):
    def has_permission(self, request, view):
        return request.user.username == 'vmix_user' or 'blake' and request.method in ['GET', 'HEAD', 'OPTIONS']

class APICompetitionDetailView(generics.RetrieveAPIView):
    queryset = Competition.objects.all()
    serializer_class = CompetitionSerializer
    lookup_field = 'id'
    permission_classes = [IsAuthenticated, IsReadOnlyUser]

class APIAthleteCompetitionDetailView(generics.RetrieveAPIView):
    queryset = AthleteCompetition.objects.all()
    serializer_class = AthleteCompetitionSerializer
    lookup_field = 'id'

class CompetitionByStatusView(generics.ListAPIView):
    serializer_class = CompetitionSerializer

    def get_queryset(self):
        status = self.kwargs['status']
        return Competition.objects.filter(status=status)