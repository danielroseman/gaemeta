import datetime

from django.contrib import admin
from django.contrib import messages
from django.contrib.admin import helpers, widgets
from django.contrib.admin.options import BaseModelAdmin, csrf_protect_m, get_ul_class
from django.contrib.admin.views.main import ChangeList, ORDER_VAR
from django.contrib.admin.utils import model_ngettext, quote
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import NoReverseMatch, reverse
from django import forms
from django.template.response import TemplateResponse
from django.utils.html import format_html, escape
from django.utils.encoding import force_text
from django.utils.text import capfirst, Truncator
from django.utils.translation import string_concat, ugettext as _, ugettext_lazy
from google.appengine.ext import ndb
from google.appengine.ext.ndb import metadata

from meta.forms import NdbBaseInlineFormSet
from meta import models


class KeyRawIdWidget(widgets.ForeignKeyRawIdWidget):
  def label_for_value(self, value):
    key = ndb.Key(urlsafe=value)
    obj = key.get()
    if obj:
      return '&nbsp;<strong>%s</strong>' % escape(Truncator(obj).words(14, truncate='...'))
    else:
      return ''


class MultipleKeyRawIdWidget(widgets.ManyToManyRawIdWidget, forms.Textarea, forms.TextInput):
  #def render(self, *args, **kwargs):
    #import pdb; pdb.set_trace()
    #super(MultipleKeyRawIdWidget, self).render(*args, **kwargs)

  def label_for_value(self, value):
    return ''

class BaseNdbAdmin(BaseModelAdmin):
  actions_selection_counter = False
  formfield_overrides = {
      models.DateTimePropertyWrapper: {
          'form_class': forms.SplitDateTimeField,
          'widget': widgets.AdminSplitDateTime
      },
      models.DatePropertyWrapper: {'widget': widgets.AdminDateWidget},
      models.TimePropertyWrapper: {'widget': widgets.AdminTimeWidget},
      models.TextPropertyWrapper: {'widget': widgets.AdminTextareaWidget},
      models.IntegerPropertyWrapper: {'widget': widgets.AdminIntegerFieldWidget},
      models.StringPropertyWrapper: {'widget': widgets.AdminTextInputWidget},
  }
  extra_widgets = {
      'raw_id_foreignkey': KeyRawIdWidget,
  }
  def has_add_permission(self, request):
    return True
  def has_change_permission(self, request, obj=None):
    return True
  def has_delete_permission(self, request, obj=None):
    return True
  def has_module_permission(self, request):
    return True
  def log_addition(self, request, object, message):
    pass
  def log_change(self, request, object, message):
    pass
  def log_deletion(self, request, object, object_repr):
    pass
  def get_object(self, request, object_id, from_field=None):
    return ndb.Key(urlsafe=object_id).get()
  def get_queryset(self, request, *args, **kwargs):
    qs = self.model.query()
    ordering = self.get_ordering(request)
    if ordering:
      qs = qs.order_by(*ordering)
    # Django clones querysets in order to modify them without changing the original.
    # But ndb queries are immutable; we can simply return the query.
    qs._clone = lambda: qs
    return qs
  def get_changelist(self, request, **kwargs):
    return NdbChangeList
  def get_pk_value_for_object(self, obj):
    return obj.key.urlsafe()
  @csrf_protect_m
  def changeform_view(self, *args, **kwargs):
    return self._changeform_view(*args, **kwargs)
  def get_deleted_objects(self, obj, user):
    return [obj], {obj._meta.verbose_name_plural: 1}, [], False
  def get_content_type(self):
    ct = metadata.Kind(key=ndb.Key('__kind__', self.model._get_kind()))
    ct.pk = ct.key
    return ct
  def get_deletion_form_class(self, base_model_form):
    return base_model_form
  def filter_queryset(self, queryset, selected):
    return selected
  def formfield_for_foreignkey(self, db_field, request=None, **kwargs):
    if db_field.name in self.raw_id_fields:
      if db_field.property._repeated:
        kwargs['widget'] = MultipleKeyRawIdWidget(
            db_field.remote_field, self.admin_site)
      else:
        kwargs['widget'] = KeyRawIdWidget(
            db_field.remote_field, self.admin_site)
    elif db_field.property._repeated and db_field.name in (list(self.filter_vertical) + list(self.filter_horizontal)):
      kwargs['widget'] = widgets.FilteredSelectMultiple(
        db_field.verbose_name,
        db_field.name in self.filter_vertical
      )
    elif db_field.name in self.radio_fields:
      kwargs['widget'] = widgets.AdminRadioSelect(attrs={
        'class': get_ul_class(self.radio_fields[db_field.name]),
      })
      kwargs['empty_label'] = _('None') if db_field.blank else None
      if 'queryset' not in kwargs:
        queryset = self.get_field_queryset(None, db_field, request)
        if queryset is not None:
          kwargs['queryset'] = queryset
    form_field = db_field.formfield(**kwargs)
    if isinstance(form_field.widget, forms.SelectMultiple) and not isinstance(form_field.widget, forms.CheckboxSelectMultiple):
      msg = _('Hold down "Control", or "Command" on a Mac, to select more than one.')
      help_text = form_field.help_text
      form_field.help_text = string_concat(help_text, ' ', msg) if help_text else msg
    return form_field

class KwargFieldListFilter(admin.filters.FieldListFilter):
  """Intermediate class to make ListFilters ndb-compatible.

  Removes double-underscore syntax from lookup kwargs, and performs ndb queries.
  If the `is_key` class attribute is True, will convert the lookup value to a
  key before querying.
  """
  def __init__(self, field, request, params, model, model_admin, field_path):
    self.lookup_kwarg = field_path
    self.lookup_val = request.GET.get(self.lookup_kwarg)
    self.model = model
    super(KwargFieldListFilter, self).__init__(
        field, request, params, model, model_admin, field_path)

  def convert_value(self, val):
    return val

  def queryset(self, request, queryset):
    for field, val in self.used_parameters.items():
      if field == getattr(self, 'lookup_kwarg_isnull', None):
        val = None
        field = self.lookup_kwarg
      else:
        val = self.convert_value(val)
      queryset = queryset.filter(self.model._properties[field]==val)
    return queryset


class NdbChoiceFieldFilter(admin.filters.ChoicesFieldListFilter, KwargFieldListFilter):
  pass
admin.filters.FieldListFilter.register(lambda f: bool(f.choices), NdbChoiceFieldFilter, True)


class NdbRelatedFieldListFilter(admin.filters.RelatedFieldListFilter, KwargFieldListFilter):
  def convert_value(self, val):
    return ndb.Key(urlsafe=val)
admin.filters.FieldListFilter.register(lambda f: f.remote_field, NdbRelatedFieldListFilter, True)

class BooleanFieldListFilter(admin.filters.BooleanFieldListFilter, KwargFieldListFilter):
  def convert_value(self, val):
    return bool(int(val))
admin.filters.FieldListFilter.register(lambda f: isinstance(f.property, ndb.BooleanProperty), BooleanFieldListFilter, True)

class DateFieldListFilter(admin.filters.DateFieldListFilter, KwargFieldListFilter):
  def queryset(self, request, queryset):
    for field, val in self.used_parameters.items():
      val = self.convert_value(val)
      if field == self.lookup_kwarg_since:
        queryset = queryset.filter(self.model._properties[self.field_path]>=val)
      elif field == self.lookup_kwarg_until:
        queryset = queryset.filter(self.model._properties[self.field_path]<val)
    return queryset

  def convert_value(self, val):
    return datetime.datetime.strptime(val, '%Y-%m-%d').date()
admin.filters.FieldListFilter.register(lambda f: isinstance(f.property, ndb.DateProperty), DateFieldListFilter, True)


class NdbChangeList(ChangeList):
  def get_ordering(self, request, queryset):
    params = self.params
    ordering = list(self.model_admin.get_ordering(request)
                    or self._get_default_ordering())
    if ORDER_VAR in params:
      # Clear ordering and used params
      ordering = []
      order_params = params[ORDER_VAR].split('.')
      for p in order_params:
        try:
          none, pfx, idx = p.rpartition('-')
          field_name = self.list_display[int(idx)]
          order_field = self.get_ordering_field(field_name)
          if not order_field:
            continue  # No 'admin_order_field', skip it
          # reverse order if order_field has already "-" as prefix
          if order_field.startswith('-') and pfx == "-":
            ordering.append(self.model._properties[order_field[1:]])
          else:
            field = self.model._properties[order_field]
            if pfx == '-':
              ordering.append(-field)
            else:
              ordering.append(field)
        except (IndexError, ValueError, KeyError):
          continue  # Invalid ordering specified, skip it.

    queryset = queryset.order(*ordering)
    return queryset

  def get_queryset(self, request):
    # First, we collect all the declared list filters.
    (self.filter_specs, self.has_filters, remaining_lookup_params,
      filters_use_distinct) = self.get_filters(request)
    queryset = self.root_queryset
    queryset = self.get_ordering(request, queryset)
    for filter_spec in self.filter_specs:
        new_queryset = filter_spec.queryset(request, queryset)
        if new_queryset is not None:
            queryset = new_queryset
    # order/filter return a new query so we need to re-annotate the fake _clone method.
    queryset._clone = lambda: queryset
    return queryset


class NdbAdmin(BaseNdbAdmin, admin.ModelAdmin):
    pass


class TabularNdbInline(BaseNdbAdmin, admin.TabularInline):
    formset = NdbBaseInlineFormSet


def delete_selected(modeladmin, request, keys):
  keys = [ndb.Key(urlsafe=k) for k in keys]
  opts = modeladmin.model._meta
  app_label = opts.app_label

  # Check that the user has delete permission for the actual model
  if not modeladmin.has_delete_permission(request):
    raise PermissionDenied
  if request.POST.get('post'):
      n = len(keys)
      if n:
        #for obj in queryset:
            #obj_display = force_text(obj)
            #modeladmin.log_deletion(request, obj, obj_display)
        ndb.delete_multi(keys)
        modeladmin.message_user(request, _("Successfully deleted %(count)d %(items)s.") % {
            "count": n, "items": model_ngettext(modeladmin.opts, n)
        }, messages.SUCCESS)
      # Return None to display the change list page again.
      return None

  deletable_objects = []
  objects = ndb.get_multi(keys)
  for obj in objects:
    try:
      admin_url = reverse('%s:%s_%s_change'
                          % (modeladmin.admin_site.name,
                             opts.app_label,
                             opts.model_name),
                          None, (obj.pk,))
    except NoReverseMatch:
      # Change url doesn't exist -- don't display link to edit
      link = '%s: %s' % (capfirst(opts.verbose_name), force_text(obj))
    else:
      link =  format_html('{}: <a href="{}">{}</a>',
                       capfirst(opts.verbose_name),
                       admin_url,
                       obj)
    deletable_objects.append(link)
  if len(keys) == 1:
    objects_name = force_text(opts.verbose_name)
  else:
    objects_name = force_text(opts.verbose_name_plural)
  title = _("Are you sure?")
  context = dict(
    modeladmin.admin_site.each_context(request),
    title=title,
    objects_name=objects_name,
    deletable_objects=[deletable_objects],
    model_count=((objects_name, len(keys)),),
    queryset=objects,
    #perms_lacking=perms_needed,
    #protected=protected,
    opts=opts,
    action_checkbox_name=helpers.ACTION_CHECKBOX_NAME,
    media=modeladmin.media,
  )

  request.current_app = modeladmin.admin_site.name

  # Display the confirmation page
  return TemplateResponse(request, modeladmin.delete_selected_confirmation_template or [
      "admin/%s/%s/delete_selected_confirmation.html" % (app_label, opts.model_name),
      "admin/%s/delete_selected_confirmation.html" % app_label,
      "admin/delete_selected_confirmation.html"
  ], context)

delete_selected.short_description = ugettext_lazy("Delete selected %(verbose_name_plural)s")

class NdbAdminSite(admin.AdminSite):
  def __init__(self, name='admin'):
    self._registry = {}  # model_class class -> admin_class instance
    self.name = name
    self._actions = {'delete_selected': delete_selected}
    self._global_actions = self._actions.copy()
  def register(self, model_or_iterable, admin_class=None, **options):
    if not admin_class:
      admin_class = NdbAdmin
    if isinstance(model_or_iterable, models.NdbModelMeta):
      model_or_iterable = [model_or_iterable]
    return super(NdbAdminSite, self).register(model_or_iterable, admin_class, **options)
  def has_permission(self, request):
    return True
  def check_dependencies(self):
    pass

site = NdbAdminSite()

site.register([models.User])
