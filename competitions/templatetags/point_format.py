from django import template
import logging

register = template.Library()
logger = logging.getLogger(__name__)

@register.filter
def format_points(value):
    if value is None:
        logger.debug("format_points: Value is None")
        return ''
    try:
        # Ensure value is treated as a number, even if pre-rendered as string
        decimal_value = float(str(value))
        logger.debug(f"format_points: Input={value}, Type={type(value)}, Float={decimal_value}")
        if decimal_value.is_integer():
            result = int(decimal_value)
            logger.debug(f"Integer case: {result}")
            return result
        result = f"{decimal_value:.1f}"
        logger.debug(f"Decimal case: {result}")
        return result
    except (ValueError, TypeError) as e:
        logger.error(f"format_points error: {e}, Value={value}")
        return str(value)  # Fallback to raw string