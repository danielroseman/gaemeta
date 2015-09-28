from django import template
register = template.Library()

@register.simple_tag
def get_admin_log(*args, **kwargs):
  return ''
