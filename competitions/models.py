from django.core.validators import MinValueValidator
from django.db import models
from django.conf import settings


from accounts.models import User, AthleteProfile

from tinymce.models import HTMLField

class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name

class Federation(models.Model):
    name = models.CharField(max_length=255)
    logo = models.ImageField(upload_to='federation_logos/')  # Add logo field

    def __str__(self):
        return self.name


class Competition(models.Model):
    """
    Represents a strongman competition with details, divisions, events, and weight classes.
    """
    STATE_CHOICES = [
        ('AL', 'Alabama'), ('AK', 'Alaska'), ('AZ', 'Arizona'), ('AR', 'Arkansas'),
        ('CA', 'California'), ('CO', 'Colorado'), ('CT', 'Connecticut'), ('DE', 'Delaware'),
        ('FL', 'Florida'), ('GA', 'Georgia'), ('HI', 'Hawaii'), ('ID', 'Idaho'),
        ('IL', 'Illinois'), ('IN', 'Indiana'), ('IA', 'Iowa'), ('KS', 'Kansas'),
        ('KY', 'Kentucky'), ('LA', 'Louisiana'), ('ME', 'Maine'), ('MD', 'Maryland'),
        ('MA', 'Massachusetts'), ('MI', 'Michigan'), ('MN', 'Minnesota'), ('MS', 'Mississippi'),
        ('MO', 'Missouri'), ('MT', 'Montana'), ('NE', 'Nebraska'), ('NV', 'Nevada'),
        ('NH', 'New Hampshire'), ('NJ', 'New Jersey'), ('NM', 'New Mexico'), ('NY', 'New York'),
        ('NC', 'North Carolina'), ('ND', 'North Dakota'), ('OH', 'Ohio'), ('OK', 'Oklahoma'),
        ('OR', 'Oregon'), ('PA', 'Pennsylvania'), ('RI', 'Rhode Island'), ('SC', 'South Carolina'),
        ('SD', 'South Dakota'), ('TN', 'Tennessee'), ('TX', 'Texas'), ('UT', 'Utah'),
        ('VT', 'Vermont'), ('VA', 'Virginia'), ('WA', 'Washington'), ('WV', 'West Virginia'),
        ('WI', 'Wisconsin'), ('WY', 'Wyoming')
    ]

    name = models.CharField(max_length=255)
    comp_date = models.DateField()
    comp_end_date = models.DateField(null=True, blank=True)
    location = models.CharField(max_length=255, null=True, blank=True)
    start_time = models.TimeField(null=True, blank=True)
    organizer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='organized_competitions')

    # Competition Details
    image = models.ImageField(upload_to='competition_images/', null=True, blank=True,
                              default='competition_images/default_competition_image2.jpg')
    capacity = models.PositiveIntegerField(default=100)
    description = HTMLField(blank=True)  # Rich text description
    liability_waiver = models.TextField(blank=True)
    scoring_system = models.CharField(max_length=50)

    # Location Details
    event_location_name = models.CharField(max_length=255, blank=True)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=255, blank=True)
    state = models.CharField(max_length=255, blank=True)
    zip_code = models.CharField(max_length=10, blank=True)

    # Federation & Sponsors
    federation = models.ForeignKey('Federation', on_delete=models.SET_NULL, null=True, blank=True, related_name='competitions')
    sponsor_logos = models.ManyToManyField('Sponsor', blank=True)

    # Social Media
    facebook_url = models.URLField(blank=True, null=True, help_text="Facebook page URL for the competition")
    instagram_url = models.URLField(blank=True, null=True, help_text="Instagram profile URL for the competition")

    # Registration & Pricing
    registration_deadline = models.DateTimeField()
    signup_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00,
                                       validators=[MinValueValidator(0.00)])

    # Allowed Categories
    allowed_divisions = models.ManyToManyField('Division', related_name='competitions_allowed_divisions')


    # Status & Approvals
    STATUS_CHOICES = [
        ('upcoming', 'Upcoming'),
        ('full', 'Full'),
        ('completed', 'Completed'),
        ('canceled', 'Canceled'),
        ('limited', 'Limited'),
        ('closed', 'Closed'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)

    APPROVAL_STATUS_CHOICES = [
        ('approved', 'Approved'),
        ('waiting', 'Waiting'),
    ]
    approval_status = models.CharField(max_length=10, choices=APPROVAL_STATUS_CHOICES,
                                       default='waiting', help_text="Admin approval status")

    PUBLICATION_STATUS_CHOICES = [
        ('published', 'Published'),
        ('unpublished', 'Unpublished'),
    ]
    publication_status = models.CharField(max_length=12, choices=PUBLICATION_STATUS_CHOICES,
                                          default='unpublished', help_text="Organizer publication status")

    email_notifications = models.BooleanField(default=False, help_text="Email organizer when athlete signs up")

    provides_shirts = models.BooleanField(default=False, help_text="Check if T-shirts are provided")
    allowed_tshirt_sizes = models.ManyToManyField('TshirtSize', blank=True)

    def get_ordered_events(self):
        return self.events.order_by('order')

    def __str__(self):
        return self.name

class Division(models.Model):
    PREDEFINED_CHOICES = [
        ('novice', 'Novice'),
        ('teen', 'Teen'),
        ('master', 'Master'),
        ('open', 'Open'),
        ('adaptive', 'Adaptive'),
        ('pro', 'Pro'),
    ]

    predefined_name = models.CharField(
        max_length=50,
        choices=PREDEFINED_CHOICES,
        blank=True,
        null=True,
        help_text="Choose a predefined name or leave blank to set a custom name."
    )
    custom_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Provide a custom division name if none of the predefined names apply."
    )
    competition = models.ForeignKey(
        'competitions.Competition',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='custom_divisions',
        help_text="Competition this custom division belongs to."
    )
    is_custom = models.BooleanField(default=False)

    def __str__(self):
        # Return custom_name if it exists; otherwise, return predefined_name
        return self.custom_name or self.name or "Unnamed Division"

    @property
    def name(self):
        return self.custom_name or self.predefined_name or "Unnamed Division"


class WeightClass(models.Model):
    """
    Model to store weight class information.
    """
    WEIGHT_CHOICES = [
        ('u', 'u'),
        ('+', '+')
    ]
    CATEGORY_CHOICES = [
        ('lw', 'LW'),
        ('mw', 'MW'),
        ('hw', 'HW'),
        ('shw', 'SWH'),
    ]
    name = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, verbose_name="Weight")
    gender = models.CharField(max_length=10, choices=[('Male', 'Male'), ('Female', 'Female')])  # Add gender field
    federation = models.ForeignKey(
        Federation,
        on_delete=models.CASCADE,
        related_name="weight_classes",
        help_text="Federation that defines this weight class."
    )
    weight_d = models.CharField(max_length=2, choices=WEIGHT_CHOICES)
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default='middleweight',
        help_text="Weight class category (e.g., lightweight, middleweight)."
    )
    division = models.ForeignKey(
        'competitions.Division',
        on_delete=models.CASCADE,
        related_name="weight_classes",
        null=True,
        blank=True,
        help_text="Division that this weight class belongs to."
    )
    is_custom = models.BooleanField(default=False)

    class Meta:
        unique_together = ('name', 'gender', 'division')

    def __str__(self):
        return f"{self.name} ({self.gender}) - {self.division.name if self.division else 'No Division'}"



class TshirtSize(models.Model):
    SIZE_CHOICES = [
        ('XS', 'Extra Small'),
        ('S', 'Small'),
        ('M', 'Medium'),
        ('L', 'Large'),
        ('XL', 'Extra Large'),
        ('XXL', '2X Large'),
        ('XXXL', '3X Large'),
    ]
    size = models.CharField(max_length=5, choices=SIZE_CHOICES, unique=True)

    def __str__(self):
        return self.get_size_display()

class CommentatorNote(models.Model):
    competition = models.ForeignKey(Competition, on_delete=models.CASCADE)
    athlete = models.ForeignKey(AthleteProfile, on_delete=models.CASCADE)
    commentator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    note = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)  # Add created_at field

    def __str__(self):
        return f"Note for {self.athlete.user.get_full_name()} at {self.competition.name}"

class Sponsor(models.Model):
    name = models.CharField(max_length=255)
    logo = models.ImageField(upload_to='sponsor_logos/')
    url = models.URLField(blank=True, null=True)  # Optional URL field
    display_order = models.PositiveIntegerField(default=0)  # For sorting logos

    def __str__(self):
        return self.name

class EventBase(models.Model):
    """
    Model representing the base movement for a strongman event.
    """
    name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.name


class Event(models.Model):
    """
       Represents an event in a competition.
    """
    name = models.CharField(max_length=80, unique=False)
    competition = models.ForeignKey(Competition, on_delete=models.CASCADE, related_name='events')
    event_base = models.ForeignKey(EventBase, on_delete=models.SET_NULL, null=True)
    order = models.PositiveSmallIntegerField(default=1)  # Order now lives in Event
    weight_type = models.CharField(max_length=20, choices=[
        ('time', 'Time'),
        ('distance', 'Distance'),
        ('max', 'Max Weight'),
        ('height', 'Height'),
        ('reps', 'Reps'),
    ])
    has_multiple_implements = models.BooleanField(
        default=False,
        help_text="Check if the event has multiple implements."
    )
    number_of_implements = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Number of implements if the event has multiple implements."
    )
    number_of_lanes = models.PositiveIntegerField(
        default=1,
        help_text="Number of lanes for this event. Set to 1 for single-lane events."
    )

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.name} (Order {self.order})"



class EventImplement(models.Model):
    """
    Represents an implement used in an event (e.g., Sandbag, Log Press).
    """
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='implements')
    division = models.ForeignKey(Division, on_delete=models.CASCADE, related_name='event_implements')
    weight_class = models.ForeignKey(WeightClass, on_delete=models.CASCADE, related_name='event_implements')
    implement_name = models.CharField(max_length=100, blank=True, help_text="Name of the implement (e.g., Log, Sandbag).")
    implement_order = models.PositiveIntegerField(default=1, help_text="Order of the implement within the event.")
    weight = models.IntegerField(help_text="Weight of the implement.")
    weight_unit = models.CharField(
        max_length=20,
        choices=[('lbs', 'lbs'), ('kg', 'kg')],
        default='lbs',
        help_text="Weight unit (lbs or kg)."
    )

    class Meta:
        ordering = ['event', 'implement_order']  # Ensure correct ordering of implements

    def __str__(self):
        base_str = f"{self.weight} {self.weight_unit} - {self.division.name} ({self.weight_class.name})"
        if self.implement_name:
            return f"{self.implement_name} - {base_str}"
        return f"Implement {self.implement_order} - {base_str}"


class AthleteCompetition(models.Model):
    """
        Links athletes to competitions, tracking division and weight class.
    """
    athlete = models.ForeignKey(AthleteProfile, on_delete=models.CASCADE)
    competition = models.ForeignKey(Competition, on_delete=models.CASCADE)
    registration_date = models.DateTimeField(auto_now_add=True)
    payment_status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('canceled', 'Canceled'),
        ('refunded', 'Refunded'),
        ('paid', 'Paid')
    ])
    registration_status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('complete', 'Complete'),
        ('canceled', 'Canceled'),
    ], default='pending')
    signed_up = models.BooleanField(default=False)
    division = models.ForeignKey(Division, on_delete=models.CASCADE, null=True, blank=True)
    weight_class = models.ForeignKey(WeightClass, on_delete=models.CASCADE, null=True, blank=True)
    total_points = models.PositiveIntegerField(default=0)
    rank = models.PositiveIntegerField(null=True, blank=True)
    tshirt_size = models.ForeignKey(
        TshirtSize,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="T-shirt size for the participant (if applicable)."
    )
    weigh_in = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Athlete's weight (lbs) recorded at the competition weigh-in."
    )


    class Meta:
        unique_together = ('athlete', 'competition')

    def get_results_for_event(self, event_order):
        return self.result_set.filter(event_order=event_order).first()

    def __str__(self):
        return f"{self.athlete.user.username} - {self.competition.name}"

class Result(models.Model):
    """
    Stores the performance results for an athlete in a competition event.
    """
    athlete_competition = models.ForeignKey(
        AthleteCompetition, on_delete=models.CASCADE, related_name='results'
    )
    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="results"
    )
    points_earned = models.PositiveIntegerField(default=0, help_text="Points awarded based on performance.")
    event_rank = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Ranking in the event.")
    time = models.DurationField(null=True, blank=True, help_text="Recorded time for time-based events.")
    value = models.CharField(
        max_length=255,
        blank=True,
        help_text="Performance value (e.g., weight lifted, distance, reps, etc.)."
    )

    class Meta:
        ordering = ["event__order", "event_rank"]  # Sort results by event order and rank

    def __str__(self):
        return f"{self.athlete_competition.athlete.user.get_full_name()} - {self.event.name}"


class ZipCode(models.Model):
    zip_code = models.CharField(max_length=5, primary_key=True)
    latitude = models.FloatField()
    longitude = models.FloatField()

    def __str__(self):
        return self.zip_code


class AthleteEventNote(models.Model):
    """
    Stores event-specific notes for athletes in a competition.
    Used for tracking custom data like yoke heights, opening weights, etc.
    """
    athlete_competition = models.ForeignKey(AthleteCompetition, on_delete=models.CASCADE, related_name='event_notes')
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    note_type = models.CharField(max_length=100, blank=True,
                                 help_text="Type of note (e.g., 'yoke_height', 'opening_weight')")
    note_value = models.CharField(max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('athlete_competition', 'event', 'note_type')
        ordering = ['event__order', 'note_type']

    def __str__(self):
        return f"{self.athlete_competition.athlete.user.get_full_name()} - {self.event.name} - {self.note_type}"


class LaneAssignment(models.Model):
    """
    Tracks lane assignments for athletes in multi-lane events.
    """
    athlete_competition = models.ForeignKey(
        AthleteCompetition,
        on_delete=models.CASCADE,
        related_name='lane_assignments'
    )
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='lane_assignments'
    )
    lane_number = models.PositiveIntegerField(
        help_text="Lane number assigned to this athlete for this event."
    )
    heat_number = models.PositiveIntegerField(
        default=1,
        help_text="Heat number for events with multiple heats."
    )

    class Meta:
        unique_together = ('athlete_competition', 'event')
        ordering = ['event', 'heat_number', 'lane_number']

    def __str__(self):
        return f"{self.athlete_competition.athlete.user.get_full_name()} - {self.event.name} - Lane {self.lane_number}, Heat {self.heat_number}"


from django.db import models
from django.utils import timezone


class CompetitionRunOrder(models.Model):
    """
    Tracks the current lifting order for a specific event in a competition.
    """
    competition = models.ForeignKey('Competition', on_delete=models.CASCADE, related_name='run_orders')
    event = models.ForeignKey('Event', on_delete=models.CASCADE, related_name='run_orders')

    athlete_competition = models.ForeignKey('AthleteCompetition', on_delete=models.CASCADE, related_name='run_orders')

    ORDER_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('current', 'Current'),
        ('completed', 'Completed'),
    ]

    status = models.CharField(
        max_length=20,
        choices=ORDER_STATUS_CHOICES,
        default='pending'
    )

    order = models.PositiveIntegerField()

    # Optional fields for additional context
    lane_number = models.PositiveIntegerField(null=True, blank=True)
    heat_number = models.PositiveIntegerField(null=True, blank=True)

    # Tracking timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['event', 'order']
        unique_together = [
            ['competition', 'event', 'order'],
            ['competition', 'event', 'athlete_competition']
        ]

    def __str__(self):
        return (f"{self.athlete_competition.athlete.user.get_full_name()} - "
                f"{self.event.name} (Order {self.order}, Status: {self.status})")