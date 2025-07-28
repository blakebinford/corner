import json
from django.core.validators import MinValueValidator
from django.db import models
from django.conf import settings
from django.utils.text import slugify
from django.utils.html import strip_tags
from django.urls import reverse
from django.utils.timezone import make_aware, get_current_timezone
from datetime import datetime, time

from accounts.models import User, AthleteProfile

from tinymce.models import HTMLField
from meta.models import ModelMeta

class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name

class Federation(models.Model):
    name = models.CharField(max_length=255)
    logo = models.ImageField(upload_to='federation_logos/')  # Add logo field

    def __str__(self):
        return self.name


class Competition(ModelMeta, models.Model):
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
    slug = models.SlugField(unique=True, blank=True, null=True)
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
    tags = models.ManyToManyField(Tag, blank=True)
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
    registration_open_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When registration becomes available. Countdown will be shown until this time."
    )

    publish_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this competition should automatically become published."
    )
    email_notifications = models.BooleanField(default=False, help_text="Email organizer when athlete signs up")

    provides_shirts = models.BooleanField(default=False, help_text="Check if T-shirts are provided")
    allowed_tshirt_sizes = models.ManyToManyField('TshirtSize', blank=True)
    current_event = models.ForeignKey(
        'Event',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='current_for_competitions'
    )
    _metadata = {
        'title': 'get_meta_title',
        'description': 'get_meta_description',
        'image': 'get_meta_image',
        'url': 'get_meta_url',
        'object_type': 'get_meta_object_type',
        'site_name': 'get_meta_site_name',
    }

    def schema_type(self):
        return "Event"

    _schema = {
        '@type': 'schema_type',
        'name': 'name',
        'description': 'get_meta_description',
        'image': 'get_meta_image',
        'startDate': 'get_schema_start_datetime',
        'location': 'get_schema_location',
        'url': 'get_meta_url',
    }

    def get_schema_start_datetime(self):
        if self.comp_date and self.start_time:
            dt = datetime.combine(self.comp_date, self.start_time)
            return make_aware(dt, get_current_timezone()).isoformat()
        elif self.comp_date:
            # Fallback: assume midnight if no start_time set
            dt = datetime.combine(self.comp_date, time(0, 0))
            return make_aware(dt, get_current_timezone()).isoformat()
        return None

    def get_schema_location(self):
        return {
            "@type": "Place",
            "name": self.event_location_name or self.location or "Competition Venue",
            "address": {
                "@type": "PostalAddress",
                "streetAddress": self.address or "",
                "addressLocality": self.city or "",
                "addressRegion": self.state or "",
                "postalCode": self.zip_code or "",
                "addressCountry": "US"
            }
        }

    def get_meta_title(self):
        return self.name

    def get_meta_description(self):
        return strip_tags(self.description)[:160]

    def get_meta_image(self):
        if self.image:
            return self.image.url
        return None

    def get_meta_url(self):
        return f"https://atlascompetition.com/competitions/{self.slug}/"

    def get_meta_object_type(self):
        return 'Event'

    def get_meta_site_name(self):
        return 'Atlas Competition'

    auto_summary = models.TextField(blank=True, null=True)

    def generate_auto_summary(self):
        from competitions.utils import generate_short_description
        if not self.auto_summary:
            self.auto_summary = generate_short_description(self)
            self.save()

    def is_published(self):
        return self.publication_status == 'published'

    def is_registration_open(self):
        return not self.registration_open_at or timezone.now() >= self.registration_open_at

    def is_visible(self):
        return self.is_published() and self.approval_status == 'approved'

    def has_full_access(self, user):
        return user == self.organizer or self.staff.filter(user=user, role='full').exists()

    def has_limited_access(self, user):
        return self.staff.filter(user=user, role='limited').exists()

    def has_any_access(self, user):
        return self.has_full_access(user) or self.has_limited_access(user)

    def set_current_event(self, event):
        self.current_event = event
        self.save(update_fields=['current_event'])

    def get_ordered_events(self):
        return self.events.order_by('order')

    def get_absolute_url(self):
        return reverse('competitions:competition_detail', kwargs={'slug': self.slug})

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug and self.name:
            base_slug = slugify(self.name)
            slug = base_slug
            i = 1
            while Competition.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{i}"
                i += 1
            self.slug = slug
        super().save(*args, **kwargs)

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
    competition = models.ForeignKey(
        'competitions.Competition',
        on_delete=models.CASCADE,
        related_name='weight_classes',
        null=True,  # TEMPORARY
        blank=True,  # TEMPORARY
        help_text="Competition this weight class belongs to."
    )

    class Meta:
        unique_together = ('name', 'gender', 'division', 'competition')

    def __str__(self):
        # 1) Custom “single class” (no name at all)
        if self.is_custom and not self.name:
            return f"{self.division.name} – Single Class"

        # 2) Under classes: prefix “u”
        if self.weight_d == 'u':
            label = f"u{self.name}"

        # 3) Plus classes: suffix “+”
        else:
            label = f"{self.name}+"

        # Always include division afterward
        return f"{label} – {self.division.name}"



class TshirtSize(models.Model):
    STYLE_CHOICES = [
        ('unisex', 'Unisex'),
        ('mens', "Men's"),
        ('womens', "Women's"),
        ('youth', 'Youth'),
    ]
    SIZE_CHOICES = [
        ('XS', 'Extra Small'),
        ('S', 'Small'),
        ('M', 'Medium'),
        ('L', 'Large'),
        ('XL', 'Extra Large'),
        ('XXL', '2X Large'),
        ('XXXL', '3X Large'),
    ]
    style = models.CharField(max_length=10,
                             choices=STYLE_CHOICES,
                             default='unisex'
                             )
    size = models.CharField(max_length=5, choices=SIZE_CHOICES)

    class Meta:
        unique_together = ('style', 'size')

    def __str__(self):
        return f"{self.get_style_display()} - {self.get_size_display()}"

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

    description = HTMLField(blank=True, null=True)

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
    implement_definition = models.ForeignKey(
        'ImplementDefinition',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='event_uses'
    )
    implement_order = models.PositiveIntegerField(default=1, help_text="Order of the implement within the event.")
    weight = models.IntegerField(help_text="Weight of the implement.",
                                 null=True,
                                 blank=True
                                 )
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
    athlete_competition = models.ForeignKey(
        AthleteCompetition, on_delete=models.CASCADE, related_name='results'
    )
    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="results"
    )
    points_earned = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        default=0,
        help_text="Points awarded based on performance (e.g., 1.5 for ties)."
    )
    event_rank = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Ranking in the event.")
    time = models.DurationField(null=True, blank=True, help_text="Recorded time for time-based events.")
    value = models.CharField(
        max_length=255,
        blank=True,
        help_text="Performance value (e.g., weight lifted, distance, reps, etc.)."
    )

    class Meta:
        ordering = ["event__order", "event_rank"]

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
    note_value_float = models.FloatField(null=True, blank=True)
    attempt_number = models.PositiveIntegerField(null=True, blank=True)
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


    def __str__(self):
        return (f"{self.athlete_competition.athlete.user.get_full_name()} - "
                f"{self.event.name} (Order {self.order}, Status: {self.status})")

UNIT_CHOICES = [
    ('lbs', 'Pounds (lbs)'),
    ('kg', 'Kilograms (kg)'),
]

class ImplementDefinition(models.Model):
    organizer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='implements'
    )
    name = models.CharField(max_length=100)
    base_weight = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    unit = models.CharField(max_length=3, choices=UNIT_CHOICES, default='lbs')
    loading_points = models.PositiveSmallIntegerField(default=2)

    class Meta:
        unique_together = ('organizer', 'name')
        ordering = ['name']

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.loading_points == 0 and self.base_weight != 0:
            raise ValidationError("Base weight must be 0 if loading points is 0.")

    def save(self, *args, **kwargs):
        if self.loading_points == 0:
            self.base_weight = 0
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.base_weight}{self.unit}, {self.loading_points} pts)"

class CompetitionStaff(models.Model):
    ROLE_CHOICES = [
        ('full', 'Full Access'),
        ('limited', 'Limited Access'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    competition = models.ForeignKey('Competition', on_delete=models.CASCADE, related_name='staff')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'competition')

# competitions/models.py

from django.db import models
from django.conf import settings

class NationalsQualifier(models.Model):
    COMPETITION_TYPE_CHOICES = [
        ('Local', 'Local'),
        ('Regional', 'Regional'),
        ('Pro/Am', 'Pro/Am'),
    ]

    athlete = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    competition = models.ForeignKey('Competition', on_delete=models.CASCADE)
    competition_type = models.CharField(max_length=20, choices=COMPETITION_TYPE_CHOICES)
    competition_date = models.DateField()

    division = models.CharField(max_length=100)
    weight_class = models.CharField(max_length=100)
    placing = models.PositiveIntegerField()

    qualification_reason = models.TextField()
    qualified_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Nationals Qualifier"
        verbose_name_plural = "Nationals Qualifiers"
        unique_together = (
            'athlete',
            'competition',
            'division',
            'weight_class',
        )

    def __str__(self):
        return f"{self.athlete.get_full_name()} - {self.competition.name} - {self.division}/{self.weight_class} ({self.placing})"
