from django.core.management.base import BaseCommand
from competitions.models import EventBase

EVENT_NAMES = [
    # Overhead Pressing
    "Log Press",
    "Axle Press",
    "Circus Dumbbell",
    "Keg Press",
    "Block Press",
    "Sandbag Press",
    "Overhead Medley",

    # Deadlifts & Pulls
    "Barbell Deadlift",
    "Axle Deadlift",
    "Car Deadlift",
    "Frame Deadlift",
    "18\" Deadlift",
    "Wagon Wheel Deadlift",
    "Silver Dollar Deadlift",
    "Max Deadlift",
    "Deadlift Medley",
    "Hummer Tire Deadlift",

    # Carries & Holds
    "Farmers Carry",
    "Yoke Carry",
    "Frame Carry",
    "Sandbag Carry",
    "Keg Carry",
    "Tombstone Carry",
    "Front Carry",
    "Zercher Carry",
    "Hercules Hold",
    "Crucifix Hold",
    "Odd Object Carry",

    # Loading & Tossing
    "Atlas Stones",
    "Stone Over Bar",
    "Keg Load",
    "Sandbag Load",
    "Sandbag to Shoulder",
    "Keg Toss",
    "Sandbag Toss",
    "Medley Load",

    # Medleys & Complexes
    "Carry Medley",
    "Load Medley",
    "Press Medley",
    "Power Stairs",
    "Chain Drag",
    "Truck Pull",
    "Sled Drag",
    "Sled Push",
    "Harness Pull",

    # Wheel-Based Events
    "Conan's Wheel",
    "Wheel of Pain",
    "Arm Over Arm Pull",

    # Grip & Armlifting
    "Rolling Thunder",
    "Silver Bullet Hold",
    "Axle Deadlift (DOH)",
    "Pinch Block Hold",
    "Vertical Bar Lift",
    "Hub Lift",
    "Wrist Roller",
    "Anvil Hold",
    "Armlifting Medley",
    "Saxon Bar",

    # Miscellaneous
    "Tug of War",
    "Mas Wrestling"
    "Other",
]

class Command(BaseCommand):
    help = "Populates the EventBase table with common strongman events"

    def handle(self, *args, **kwargs):
        created = 0
        for name in EVENT_NAMES:
            obj, was_created = EventBase.objects.get_or_create(name=name)
            if was_created:
                created += 1
        self.stdout.write(self.style.SUCCESS(f"{created} EventBase entries created."))

