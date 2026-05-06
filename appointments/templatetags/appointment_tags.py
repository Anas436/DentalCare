from django import template

register = template.Library()


@register.filter(name='format_datetime')
def format_datetime(value):
    if not value:
        return ''
    return value.strftime('%a, %b %d at %I:%M %p').replace(' 0', ' ').replace('AM', 'AM').replace('PM', 'PM')


@register.filter(name='specialization_display')
def specialization_display(value):
    if not value:
        return ''
    return value.replace('_', ' ').title()


@register.filter(name='status_badge_class')
def status_badge_class(value):
    classes = {
        'available': 'bg-green-100 text-green-800',
        'booked': 'bg-blue-100 text-blue-800',
        'cancelled': 'bg-red-100 text-red-800',
        'completed': 'bg-gray-100 text-gray-800',
    }
    return classes.get(value, 'bg-gray-100 text-gray-800')
