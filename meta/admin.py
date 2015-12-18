import datetime

from django.contrib import admin
from django.contrib.admin import helpers, widgets
from django.contrib.admin.options import BaseModelAdmin, csrf_protect_m
from django.contrib.admin.views.main import ChangeList, ORDER_VAR
from django import forms
from django.utils.safestring import mark_safe
from google.appengine.ext import ndb
from google.appengine.ext.ndb import metadata

from meta.forms import NdbBaseInlineFormSet
from meta.models import Book, Author, User
from meta import models


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
  def action_checkbox(self, obj):
    return helpers.checkbox.render(helpers.ACTION_CHECKBOX_NAME, obj.key.urlsafe())
  action_checkbox.short_description = mark_safe('<input type="checkbox" id="action-toggle" />')
  action_checkbox.allow_tags = True
  def get_deleted_objects(self, obj, user):
    return [obj], {obj._meta.verbose_name_plural: 1}, [], False
  def get_content_type(self):
    ct = metadata.Kind(key=ndb.Key('__kind__', self.model._get_kind()))
    ct.pk = ct.key
    return ct


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


class NdbAdminSite(admin.AdminSite):
  def has_permission(self, request):
    return True
  def check_dependencies(self):
    pass

site = NdbAdminSite()

class BookInline(TabularNdbInline):
  model = Book

class AuthorAdmin(NdbAdmin):
  model = Author
  inlines = [BookInline]
  list_display = ('name',)
  list_filter = ('sex',)

class BookAdmin(NdbAdmin):
  model = Book
  list_display = ('name', 'author', 'get_author', 'pages')
  list_filter = ('author',)

  def get_author(self, obj):
    return obj.author.get() if obj.author else ""
  get_author.short_description = 'Author'

site.register([Book], BookAdmin)
site.register([Author], AuthorAdmin)
site.register([User], NdbAdmin)
