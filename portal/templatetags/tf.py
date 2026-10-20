from django import template

register = template.Library()


@register.filter
def pct(value):
    """72 -> '72%'; None -> an en dash (no data is never shown as 0%)."""
    if value is None or value == "":
        return "—"
    return f"{float(value):g}%"


@register.filter
def tone(value):
    """Colour class for a percentage: good >= 75, warn >= 50, bad below, muted when there is no data."""
    if value is None or value == "":
        return "muted"
    v = float(value)
    return "good" if v >= 75 else "warn" if v >= 50 else "bad"


@register.filter
def width(value):
    """Clamp a percentage for use as a CSS width."""
    try:
        return max(0, min(100, float(value)))
    except (TypeError, ValueError):
        return 0


@register.filter
def test_state(a):
    """Display state of an assessment: a pending test whose date has passed is shown as 'missed'."""
    return "missed" if a.is_overdue else a.status.lower()


@register.filter
def test_state_label(a):
    return "Missed" if a.is_overdue else a.get_status_display()
