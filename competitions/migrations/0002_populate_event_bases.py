from django.db import migrations

def populate_event_bases(apps, schema_editor):
    """
    Function to populate the EventBase model with initial data.
    """
    EventBase = apps.get_model('competitions', 'EventBase')  # Get the EventBase model
    event_bases = [
        "Log Press", "Axle Press", "Deadlift", "Yoke Walk", "Farmers Carry",
        "Atlas Stones", "Tire Flip", "Conan's Wheel", "Sandbag Carry",
        "Keg Toss", "Car Walk", "Truck Pull", "Hercules Hold", "Stone Over Bar",
        "Carry & Drag", "Super Yoke", "Duck Walk", "Frame Carry", "Sandbag Over Bar",
        "Power Stairs", "Circus Dumbbell", "Wagon Wheel Deadlift", "Front Hold",
        "Car Deadlift", "Elephant Bar Deadlift", "Block Press", "Viking Press", "Zercher Carry",
        "Stone Load", "Cylinder Hold", "Fingal's Fingers", "Loading Race",
        "Odd Object Medley", "Sandbag Medley", "Crucifix Hold", "Hand Over Hand Truck Pull",
        "Sandbag for height", "Sandbag Throw",
    ]  # List of strongman movements
    for event_base in event_bases:
        EventBase.objects.create(name=event_base)  # Create EventBase instances

class Migration(migrations.Migration):
    """
    Migration class to apply the data migration.
    """
    dependencies = [
        ('competitions', '0001_initial'),  # Replace with the name of your previous migration
    ]

    operations = [
        migrations.RunPython(populate_event_bases),  # Run the population function
    ]