import os

from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404

from accounts.models import User, AthleteProfile
from competitions.models import Competition, AthleteCompetition
from competitions.views import ordinal, wrap_text


def competition_overlay(request, competition_pk, user_pk):
    from PIL import Image, ImageDraw, ImageFont, ImageOps

    # Fetch competition and athlete details
    competition = get_object_or_404(Competition, pk=competition_pk)
    athlete = get_object_or_404(AthleteProfile, user_id=user_pk)
    athlete_competition = AthleteCompetition.objects.filter(
        competition=competition, athlete=athlete
    ).first()
    athlete_rank = ordinal(athlete_competition.rank) if athlete_competition and athlete_competition.rank else "N/A"
    division = athlete_competition.division.name.upper() if athlete_competition else "N/A"
    weight_class_obj = athlete_competition.weight_class if athlete_competition else None
    athlete_results = athlete_competition.results.all() if athlete_competition else []

    # Process weight class
    weight_class = f"{weight_class_obj.weight_d}{weight_class_obj.name}" if weight_class_obj and weight_class_obj.weight_d == "u" else \
        f"{weight_class_obj.name}{weight_class_obj.weight_d}" if weight_class_obj else "N/A"

    # Fonts and paths
    profile_photo_path = athlete.user.profile_picture.path
    trophy_image_path = "competitions/static/competitions/images/trophy-xxl.png"
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    output_path = f"/tmp/overlay_{athlete.user.pk}_{competition.pk}.png"

    if request.method == "POST" and 'custom_photo' in request.FILES:
        custom_photo = request.FILES['custom_photo']
        temp_path = default_storage.save(f"tmp/{custom_photo.name}", ContentFile(custom_photo.read()))
        profile_photo_path = default_storage.path(temp_path)
    else:
        profile_photo_path = athlete.user.profile_picture.path  # Default to profile picture

    light_gray = "#d3dade"
    # Canvas setup
    # Canvas setup
    canvas_size = 1080  # Updated for a square canvas
    border_thickness = 50
    canvas = Image.new("RGBA", (canvas_size, canvas_size), light_gray)

    # Create dark background
    gradient = Image.new("RGBA", (canvas_size, canvas_size))
    draw_gradient = ImageDraw.Draw(gradient)
    for y in range(canvas_size):
        color = "black"
        draw_gradient.line([(0, y), (canvas_size, y)], fill=color)
    canvas = Image.alpha_composite(canvas, gradient)

    # Inner box setup
    inner_box_size = canvas_size - 2 * border_thickness
    inner_box_radius = 30  # Adjusted for rounded corners
    inner_box = Image.new("RGBA", (inner_box_size, inner_box_size), (255, 255, 255, 0))
    draw_inner_box = ImageDraw.Draw(inner_box)
    draw_inner_box.rounded_rectangle(
        [(0, 0), (inner_box_size, inner_box_size)],
        radius=inner_box_radius,
        fill="#242423",
    )
    inner_box_x, inner_box_y = border_thickness, border_thickness
    canvas.paste(inner_box, (inner_box_x, inner_box_y), inner_box)

    # Profile photo
    profile_photo_height = int(inner_box_size * 0.6)
    profile_photo = Image.open(profile_photo_path).convert("RGBA")
    profile_photo = ImageOps.fit(profile_photo, (inner_box_size, profile_photo_height), Image.Resampling.LANCZOS)

    # Create a mask for top-rounded corners
    mask = Image.new("L", profile_photo.size, 0)
    draw_mask = ImageDraw.Draw(mask)

    # Top-rounded rectangle
    corner_radius = 50  # Adjust corner radius as needed
    width, height = profile_photo.size

    # Apply rounded corners to profile photo
    mask = Image.new("L", profile_photo.size, 0)
    draw_mask = ImageDraw.Draw(mask)
    corner_radius = 30
    width, height = profile_photo.size
    draw_mask.rectangle([(0, corner_radius), (width, height)], fill=255)
    draw_mask.rectangle([(corner_radius, 0), (width - corner_radius, corner_radius)], fill=255)
    draw_mask.pieslice([(0, 0), (2 * corner_radius, 2 * corner_radius)], 180, 270, fill=255)
    draw_mask.pieslice([(width - 2 * corner_radius, 0), (width, 2 * corner_radius)], 270, 360, fill=255)
    profile_photo.putalpha(mask)
    canvas.paste(profile_photo, (inner_box_x, inner_box_y), profile_photo)

    # Fonts
    try:
        competition_font = ImageFont.truetype(font_path, 45)
        comp_font = ImageFont.truetype(font_path, 25)
        athlete_font = ImageFont.truetype(font_path, 80)
        division_font = ImageFont.truetype(font_path, 30)
        rank_font = ImageFont.truetype(font_path, 80)
        event_font = ImageFont.truetype(font_path, 30)
        place_font = ImageFont.truetype(font_path, 30)
    except OSError:
        raise OSError(f"Font file not found or invalid: {font_path}")

    draw = ImageDraw.Draw(canvas)

    # Add athlete's last name overlapping the photo
    last_name_text = athlete.user.last_name.upper()
    text_x = canvas_size // 2
    text_y = inner_box_y
    shadow_offset = 5

    draw.text((text_x + shadow_offset, text_y + shadow_offset), last_name_text, font=athlete_font, fill="black", anchor="mm")
    draw.text((text_x, text_y), last_name_text, font=athlete_font, fill="white", anchor="mm")



    # Add rounded rectangle at the bottom of the profile picture
    rectangle_width = int(inner_box_size * 0.8)
    rectangle_height = 150
    rectangle_x = inner_box_x + (inner_box_size - rectangle_width) // 2
    rectangle_y = inner_box_y + profile_photo_height - rectangle_height // 2
    draw.rounded_rectangle(
        [(rectangle_x, rectangle_y), (rectangle_x + rectangle_width, rectangle_y + rectangle_height)],
        radius=40,
        fill=(30, 30, 30),
        outline="white",
        width=5,
    )

    if athlete_rank == "1st":
        circle_fill_color = "#DED831" # Gold
    elif athlete_rank == "2nd":
        circle_fill_color = "#b3bcc7"   # Silver
    elif athlete_rank == "3rd":
        circle_fill_color = "#c47b3b"  # Bronze
    else:
        circle_fill_color = "#7EBDC2"  # Blue

    # Add circle with light blue fill extending outside the rectangle
    circle_radius = 100
    circle_x = rectangle_x + circle_radius - 20
    circle_y = rectangle_y + rectangle_height // 2
    draw.ellipse(
        [(circle_x - circle_radius, circle_y - circle_radius),
         (circle_x + circle_radius, circle_y + circle_radius)],
        fill=circle_fill_color,
    )

    # Add "Competition Corner" above the rounded rectangle
    competition_corner_text = "COMPETITION CORNER"
    text_x = canvas_size // 2.2
    text_y = rectangle_y - 15  # Position above the rounded rectangle with padding

    # Draw black outline for the text (thin stroke effect)
    outline_offset = 2
    for dx in [-outline_offset, 0, outline_offset]:
        for dy in [-outline_offset, 0, outline_offset]:
            if dx != 0 or dy != 0:  # Skip the center position
                draw.text(
                    (text_x + dx, text_y + dy),
                    competition_corner_text,
                    font=comp_font,
                    fill="black",
                    anchor="mm"
                )

    # Draw the main "Competition Corner" text in white
    draw.text(
        (text_x, text_y),
        competition_corner_text,
        font=comp_font,
        fill="white",
        anchor="mm"
    )


    # Add trophy image inside the circle
    trophy_image = Image.open(trophy_image_path).convert("RGBA")
    trophy_size = int(circle_radius * 1.5)
    trophy_image = ImageOps.fit(trophy_image, (trophy_size, trophy_size), Image.Resampling.LANCZOS)
    canvas.paste(trophy_image, (circle_x - trophy_size // 2, circle_y - trophy_size // 2), trophy_image)

    # Add "1st Place" in larger bold text
    text_x = circle_x + circle_radius + 40
    text_y = rectangle_y + rectangle_height // 2 - 15
    draw.text((text_x, text_y), f"{athlete_rank.upper()} PLACE", font=rank_font, fill="white", anchor="lm")

    # Add division and weight class in smaller text below
    draw.text((text_x, text_y + 50), f"{division} - {weight_class}", font=division_font, fill="white", anchor="lm")

    competition_name_text = competition.name.upper()
    competition_name_y = rectangle_y + rectangle_height + 60  # Position just below the rounded rectangle

    outline_offset = 2
    for dx in [-outline_offset, 0, outline_offset]:
        for dy in [-outline_offset, 0, outline_offset]:
            if dx != 0 or dy != 0:  # Skip the center position
                draw.text(
                    (canvas_size // 2 + dx, competition_name_y + dy),
                    competition_name_text,
                    font=competition_font,
                    fill="black",
                    anchor="mm"
                )

    # Draw the main competition name text in white
    draw.text(
        (canvas_size // 2, competition_name_y),
        competition_name_text,
        font=competition_font,
        fill="white",
        anchor="mm"
    )
    # Add light gray background for event performance
    event_bg_y = rectangle_y + rectangle_height + 85
    event_bg_y = competition_name_y + 75  # Add padding below the competition name
    event_bg_height = canvas_size - event_bg_y - 150

    # Add event performances in rows of 3
    cols = 5
    col_width = inner_box_size // cols
    row_height = 150
    event_x_start = inner_box_x
    event_y_start = event_bg_y

    num_events = len(athlete_results)

    for row in range((num_events + cols - 1) // cols):  # Calculate the number of rows
        # Events in the current row
        events_in_row = min(cols, num_events - row * cols)

        # Calculate horizontal offset to center the row
        row_offset = (inner_box_size - (events_in_row * col_width)) // 2

        for col in range(events_in_row):
            # Calculate the event's index and positions
            event_index = row * cols + col
            x_center = event_x_start + row_offset + col * col_width + col_width // 2
            y_top = event_y_start + row * row_height

            result = athlete_results[event_index]

            # Finishing place (above event name)
            event_rank = ordinal(result.event_rank)
            draw.text((x_center, y_top), event_rank, font=place_font, fill="#BB4430", anchor="mm")

            # Event name (below finishing place)
            event_name = result.event_order.event.name
            wrapped_event_name = wrap_text(event_name, event_font, col_width - 20)
            for line_index, line in enumerate(wrapped_event_name):
                draw.text((x_center, y_top + 50 + (line_index * 40)), line, font=event_font, fill="white", anchor="mm")

            # Draw vertical line separator (not for the last event in the row)
            if col < events_in_row - 1:
                line_x = event_x_start + row_offset + (col + 1) * col_width
                draw.line([(line_x, y_top - 20), (line_x, y_top + 100)], fill="gray", width=3)

    # Save the image
    canvas.save(output_path)
    if request.method == "POST" and 'custom_photo' in request.FILES:
        os.remove(profile_photo_path)

    return render(request, 'competitions/competition_overlay.html', {
        'competition': competition,
        'athlete': athlete,
    })

def competition_overlay_image(request, competition_pk, user_pk):

    competition = get_object_or_404(Competition, pk=competition_pk)
    athlete = get_object_or_404(AthleteProfile, user_id=user_pk)
    output_path = f"/tmp/overlay_{athlete.user.pk}_{competition.pk}.png"

    if not os.path.exists(output_path):
        return JsonResponse({"error": "Overlay image not found. Please regenerate it."}, status=404)

    with open(output_path, "rb") as img:
        return HttpResponse(img.read(), content_type="image/png")
