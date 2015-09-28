from django import forms
from django.core.exceptions import ValidationError
from django.forms.models import InlineForeignKeyField
from django.utils.text import capfirst

from google.appengine.ext import ndb

class NdbBaseInlineFormSet(forms.BaseInlineFormSet):
    @classmethod
    def get_default_prefix(cls):
      return cls.model._meta.model_name
        #return cls.fk.property._kind.lower()

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

    def add_pk_field(self, form, index):
      # Key field is never editable in an NDB model.
      if form.is_bound:
        pk_value = form.instance.id
      else:
        try:
          if index is not None:
            pk_value = self.get_queryset()[index].id
          else:
            pk_value = None
        except IndexError:
          pk_value = None
      if form._meta.widgets:
        widget = form._meta.widgets.get(self._pk_field.name, forms.HiddenInput)
      else:
        widget = forms.HiddenInput
      form.fields[self._pk_field.name] = KeyField(kind=self.model, initial=pk_value, required=False, widget=widget)

    #def save_new(self, form, commit=True):
        ## Ensure the latest copy of the related instance is present on each
        ## form (it may have been saved after the formset was originally
        ## instantiated).
        #setattr(form.instance, self.fk.name, self.instance)
        ## Use commit=False so we can assign the parent key afterwards, then
        ## save the object.
        #obj = form.save(commit=False)
        #pk_value = getattr(self.instance, self.fk.remote_field.field_name)
        #setattr(obj, self.fk.get_attname(), getattr(pk_value, 'pk', pk_value))
        #if commit:
            #obj.save()
        ## form.save_m2m() can be called via the formset later on if commit=False
        #if commit and hasattr(form, 'save_m2m'):
            #form.save_m2m()
        #return obj

    def add_fields(self, form, index):
      #self._pk_field = self.model._meta.pk
      # skip superclass, go straight to its parent
      super(forms.BaseInlineFormSet, self).add_fields(form, index)
      if self._pk_field.name == self.fk.name:
        name = self._pk_field.name
        kwargs = {'pk_field': True}
      else:
        # The foreign key field might not be on the form, so we poke at the
        # Model field to get the label, since we need that for error messages.
        name = self.fk.name
        kwargs = {
          'label': getattr(form.fields.get(name), 'label', capfirst(self.fk.verbose_name))
        }
        #if self.fk.rel.field_name != self.fk.rel.to._meta.pk.name:
          #kwargs['to_field'] = self.fk.rel.field_name
        kwargs['to_field'] = 'id'

      form.fields[name] = InlineForeignKeyField(self.instance, **kwargs)

      # Add the generated field to form._meta.fields if it's defined to make
      # sure validation isn't skipped on that field.
      if form._meta.fields:
        if isinstance(form._meta.fields, tuple):
          form._meta.fields = list(form._meta.fields)
        form._meta.fields.append(self.fk.name)

    #def initial_form_count(self):
        #"""Returns the number of forms that are required in this FormSet."""
        #if not (self.data or self.files):
            #return self.get_queryset().count()
        #return super(NdbBaseInlineFormSet, self).initial_form_count()


class KeyField(forms.ChoiceField):
  def __init__(self, *args, **kwargs):
    self.kind = kwargs.pop('kind')
    if not isinstance(self.kind, basestring):
      # assume it's a model, get its string kind
      self.kind = self.kind._get_kind()
    self.query = kwargs.pop('query', None)
    if not self.query:
      self.query = ndb.Query(kind=self.kind)
      #self.query = self.kind.query()
    forms.Field.__init__(self, *args, **kwargs)
    self.widget.choices = self.choices

  def _get_choices(self):
    if not hasattr(self, '_choices'):
      self._choices = [(x.key.urlsafe(), unicode(x)) for x in self.query.fetch()]
      if not self.required:
        self._choices.insert(0, (None, '-----'))
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
