from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.authtoken.models import Token
from rest_framework.response import Response

from .models import Competition, AthleteCompetition, Result, Event, AthleteProfile, Division, WeightClass

class DivisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Division
        fields = ['name', 'predefined_name', 'custom_name', 'is_custom']

class WeightClassSerializer(serializers.ModelSerializer):
    division = DivisionSerializer()

    class Meta:
        model = WeightClass
        fields = ['name', 'gender', 'division', 'category', 'is_custom']

class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = ['name', 'order', 'weight_type', 'number_of_lanes']

class ResultSerializer(serializers.ModelSerializer):
    event = EventSerializer()

    class Meta:
        model = Result
        fields = ['event', 'points_earned', 'event_rank', 'time', 'value']

class AthleteProfileSerializer(serializers.ModelSerializer):
    # Pull first_name, last_name, and profile_picture from User model
    first_name = serializers.CharField(source='user.first_name')
    last_name = serializers.CharField(source='user.last_name')
    full_name = serializers.CharField(source='user.get_full_name', read_only=True)
    profile_picture = serializers.ImageField(source='user.profile_picture', use_url=True)
    instagram_name = serializers.CharField(source='user.instagram_name')
    x_name = serializers.CharField(source='user.x_name')
    facebook_name = serializers.CharField(source='user.facebook_name')

    class Meta:
        model = AthleteProfile
        fields = [
            'first_name', 'last_name', 'full_name', 'profile_picture', 'instagram_name',
            'x_name', 'facebook_name', 'gender', 'nickname', 'street_number', 'city',
            'state', 'zip_code', 'phone_number', 'home_gym', 'team_name', 'coach',
            'height', 'weight', 'date_of_birth', 'whatsapp_number', 'bio'
        ]

class AthleteCompetitionSerializer(serializers.ModelSerializer):
    athlete = AthleteProfileSerializer()
    division = DivisionSerializer()
    weight_class = WeightClassSerializer()
    results = ResultSerializer(many=True)
    tshirt_size = serializers.StringRelatedField()  # Returns size like "Medium"

    class Meta:
        model = AthleteCompetition
        fields = [
            'athlete', 'division', 'weight_class', 'total_points', 'rank', 'results',
            'registration_date', 'payment_status', 'registration_status', 'signed_up',
            'tshirt_size', 'weigh_in'
        ]

class CompetitionSerializer(serializers.ModelSerializer):
    athletes = AthleteCompetitionSerializer(many=True, source='athletecompetition_set')
    events = EventSerializer(many=True)

    class Meta:
        model = Competition
        fields = ['name', 'comp_date', 'comp_end_date', 'location', 'status', 'events', 'athletes']

class GetTokenView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        token, created = Token.objects.get_or_create(user=request.user)
        return Response({'token': token.key})