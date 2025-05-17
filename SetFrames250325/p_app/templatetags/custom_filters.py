from django import template

register = template.Library()

@register.filter(name='abs')
def absolute_value(value):
    """Returns the absolute value of a number, handling SafeString"""
    try:
        # Convert to float first to handle SafeString
        return abs(float(value))
    except (ValueError, TypeError):
        return 0