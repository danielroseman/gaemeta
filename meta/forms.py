from django import forms
from django.core.exceptions import ValidationError
from django.forms.models import InlineForeignKeyField
from django.utils.text import capfirst

from google.appengine.ext import ndb


class NdbBaseModelFormSet(forms.BaseModelFormSet):
  def add_pk_field(self, form, index):
    # Key field is never editable in an NDB model.
    if form.is_bound:
      pk_value = form.instance.pk
    else:
      try:
        if index is not None:
          pk_value = self.get_queryset()[index].pk
        else:
          pk_value = None
      except IndexError:
        pk_value = None
    if form._meta.widgets:
      widget = form._meta.widgets.get(self._pk_field.name, forms.HiddenInput)
    else:
      widget = forms.HiddenInput
    form.fields[self._pk_field.name] = KeyField(kind=self.model, initial=pk_value, required=False, widget=widget)


class NdbBaseInlineFormSet(forms.BaseInlineFormSet, NdbBaseModelFormSet):
  def get_filtered_queryset(self, queryset):
    if self.instance.pk is not None:
      qs = queryset.filter(self.fk.property==self.instance.key)
    else:
      qs = queryset.filter(self.fk.property==ndb.Key(
        self.fk.property._kind, 'theresnowaythiscouldeverbearealkey'))
    return qs

  def get_queryset(self):
    if not hasattr(self, '_queryset'):
      if self.queryset is not None:
        qs = self.queryset
      else:
        qs = self.model._default_manager.get_queryset()
      if not qs.orders:
        qs = qs.order(self.model.key)
      self._queryset = qs
    return self._queryset.fetch()


class KeyField(forms.ChoiceField):
  multiple = False
  def __init__(self, *args, **kwargs):
    self.kind = kwargs.pop('kind')
    if not isinstance(self.kind, basestring):
      # assume it's a model, get its string kind
      self.kind = self.kind._get_kind()
    self.query = kwargs.pop('query', None)
    if not self.query:
      self.query = ndb.Query(kind=self.kind)
    if kwargs.get('required') and (kwargs.get('initial') is not None):
      self.empty_label = None
    else:
      self.empty_label = kwargs.pop('empty_label', "---------")
    forms.Field.__init__(self, *args, **kwargs)
    self.widget.choices = self.choices

  def _get_choices(self):
    if not hasattr(self, '_choices'):
      self._choices = [(x.key.urlsafe(), unicode(x)) for x in self.query.fetch()]
      if not self.required and not self.multiple:
        self._choices.insert(0, (None, self.empty_label))
    return self._choices

  choices = property(_get_choices, forms.ChoiceField._set_choices)

  def to_python(self, value):
    if value:
      value = ndb.Key(urlsafe=value)
      instance = value.get()
      if not instance:
        raise ValidationError(self.error_messages['invalid_choice'],
                              code='invalid_choice')
    return value or None

  def validate(self, value):
    return forms.Field.validate(self, value)

  def prepare_value(self, value):
    if isinstance(value, ndb.Key):
      return value.urlsafe()
    else:
      return value

class MultipleKeyField(KeyField):
  hidden_widget = forms.MultipleHiddenInput
  widget = forms.SelectMultiple
  multiple = True

  def to_python(self, values):
    if values:
      return [super(MultipleKeyField, self).to_python(val) for val in values]

  def prepare_value(self, values):
    if values:
      return [super(MultipleKeyField, self).prepare_value(val) for val in values]
