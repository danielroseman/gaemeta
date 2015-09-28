from django.contrib import admin
from django.contrib.admin import helpers
from django.contrib.admin.options import BaseModelAdmin, csrf_protect_m
from django.contrib.admin.views.main import ChangeList, ORDER_VAR
from django.utils.safestring import mark_safe
from google.appengine.ext import ndb
from google.appengine.ext.ndb import metadata

from meta.forms import NdbBaseInlineFormSet
from meta.models import Book, Author, User


class BaseNdbAdmin(BaseModelAdmin):
  actions_selection_counter = False
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
    # order returns a new query so we need to re-annotate the fake _clone method.
    queryset._clone = lambda: queryset
    return queryset

  def get_queryset(self, request):
    # First, we collect all the declared list filters.
    (self.filter_specs, self.has_filters, remaining_lookup_params,
      filters_use_distinct) = self.get_filters(request)
    import pdb; pdb.set_trace()
    qs = self.root_queryset
    qs = self.get_ordering(request, qs)
    return qs


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
  list_display = ('name', 'get_author', 'pages')

  def get_author(self, obj):
    return obj.author.get() if obj.author else ""
  get_author.short_description = 'Author'

site.register([Book], BookAdmin)
site.register([Author], AuthorAdmin)
site.register([User], NdbAdmin)
