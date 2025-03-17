import math

from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from competitions.models import Division, WeightClass

def get_division_weight_classes(request, division_id):
    """
    Fetches weight classes for a given division and returns them as JSON.
    """
    division = get_object_or_404(Division, id=division_id)

    # Directly fetch weight classes from the division relationship
    weight_classes = WeightClass.objects.filter(division=division)

    return JsonResponse(
        [{'id': wc.id, 'text': str(wc)} for wc in weight_classes],
        safe=False
    )

def get_weight_classes(request):
    federation_id = request.GET.get('federation_id')
    if not federation_id or not federation_id.isdigit():
        return JsonResponse({'error': 'Federation ID is required'}, status=400)

    # Fetch weight classes for the selected federation
    weight_classes = WeightClass.objects.filter(federation_id=federation_id)
    weight_class_data = [{'id': wc.id, 'name': str(wc)} for wc in weight_classes]

    return JsonResponse({'weight_classes': weight_class_data})

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great-circle distance between two points on a sphere
    given their longitudes and latitudes.
    """
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    # Haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
    c = 2 * math.asin(math.sqrt(a))

    # Radius of earth in miles
    r = 3956

    # Calculate the result
    return c * r

def ordinal(n):
    """
    Convert an integer into its ordinal representation.
    E.g. 1 => '1st', 2 => '2nd', 3 => '3rd', etc.
    """
    try:
        n = int(n)
        if 10 <= n % 100 <= 20:
            suffix = "th"
        else:
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        return f"{n}{suffix}"
    except (ValueError, TypeError):
        return "N/A"


def draw_gradient_text(draw, text, position, font, start_color, end_color):
    """
    Draws gradient text on the given ImageDraw object.

    :param draw: ImageDraw object to draw on
    :param text: Text string to render
    :param position: (x, y) starting position of the text
    :param font: Font object for the text
    :param start_color: RGB tuple for the start of the gradient (e.g., (255, 0, 0))
    :param end_color: RGB tuple for the end of the gradient (e.g., (150, 0, 0))
    """
    x, y = position

    # Calculate text width using textbbox
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]

    # Calculate gradient step for each pixel
    r_step = (end_color[0] - start_color[0]) / text_width
    g_step = (end_color[1] - start_color[1]) / text_width
    b_step = (end_color[2] - start_color[2]) / text_width

    for i, char in enumerate(text):
        char_width = draw.textbbox((0, 0), char, font=font)[2]  # Get individual character width
        r = int(start_color[0] + r_step * (x - position[0]))
        g = int(start_color[1] + g_step * (x - position[0]))
        b = int(start_color[2] + b_step * (x - position[0]))
        draw.text((x, y), char, font=font, fill=(r, g, b))
        x += char_width  # Move x position for the next character

def wrap_text(text, font, max_width):
    """Improved word wrapping for long words and proper line breaks."""
    lines, words = [], text.split()
    while words:
        line = words.pop(0)
        while words and font.getbbox(line + " " + words[0])[2] <= max_width:
            line += " " + words.pop(0)

        # Split words longer than max_width
        while font.getbbox(line)[2] > max_width and len(line) > 1:
            lines.append(line[:max_width])
            line = line[max_width:]
        lines.append(line)

    return lines


def add_gradient_rectangle(draw, x, y, width, height, start_opacity, end_opacity, color):
    """
    Adds a gradient rectangle to the given canvas.
    :param draw: ImageDraw object
    :param x: X-coordinate of the top-left corner
    :param y: Y-coordinate of the top-left corner
    :param width: Width of the rectangle
    :param height: Height of the rectangle
    :param start_opacity: Starting opacity (0-255)
    :param end_opacity: Ending opacity (0-255)
    :param color: Base color of the gradient
    """
    for i in range(height):
        opacity = start_opacity + int((end_opacity - start_opacity) * (i / height))
        fill_color = (*color, opacity)
        draw.line([(x, y + i), (x + width, y + i)], fill=fill_color)
