from django.apps import apps
from django.db.models import options
from django.db.models.base import ModelState
from django.db.models.fields import BLANK_CHOICE_DASH, NOT_PROVIDED
from django.db.models.fields.related import ManyToOneRel
from django.db.models.query_utils import PathInfo
from django import forms
from django.utils.encoding import smart_text
from django.utils.functional import cached_property
from django.utils.text import capfirst

from google.appengine.ext import ndb

from meta.forms import KeyField, MultipleKeyField

class PropertyWrapper(object):
  one_to_many = False
  one_to_one = False
  many_to_many = False
  many_to_one = False
  is_relation = False
  concrete = True
  editable = True
  unique = False
  auto_created = False
  formfield_class = forms.CharField

  def __init__(self, name, property_, model, creation_counter):
    self.name = name
    self.property = property_
    self.model = model
    self.creation_counter = creation_counter
    self.blank = self.null = not self.property._required
    self.default = getattr(self.property, '_default', NOT_PROVIDED)
    self.flatchoices = self.choices = [(x, x) for x in property_._choices or []]
    self.verbose_name = property_._verbose_name or name
    self.remote_field = None

  def __repr__(self):
    return 'PropertyWrapper: {}'.format(self.name)

  def __lt__(self, other):
    # This is needed because bisect does not take a comparison function.
    if isinstance(other, PropertyWrapper):
      return self.creation_counter < other.creation_counter
    return NotImplemented

  #@cached_property
  #def related_model(self):
    #return self.remote_field.model
  def get_choices(self, include_blank=True,
                  blank_choice=BLANK_CHOICE_DASH, limit_choices_to=None):
    return self.get_flatchoices(include_blank, blank_choice)

  def get_attname(self):
    return self.name

  def get_flatchoices(self, include_blank=True,
                      blank_choice=BLANK_CHOICE_DASH):
    first_choice = blank_choice if include_blank else []
    return first_choice + list(self.choices)

  def value_from_object(self, obj):
    value = getattr(obj, self.name)
    if isinstance(value, ndb.Key):
      value = value.urlsafe()
    return value

  def display_value(self, value):
    if isinstance(self.property, ndb.KeyProperty):
      return value.get() if value else ""
    return value

  def save_form_data(self, instance, data):
    if isinstance(self.property, ndb.KeyProperty) and isinstance(data, ndb.Model):
      data = data.key
    setattr(instance, self.name, data)

  def formfield(self, **kwargs):
    defaults = {'required': not self.blank,
                'label': capfirst(self.verbose_name),
                #'help_text': self.help_text
                }
    if self.default:
      # ndb default is always a value, not a callable
      defaults['initial'] = self.default
    if self.choices:
      defaults['choices'] = self.choices
      field_class = forms.ChoiceField
    else:
      field_class = self.formfield_class
    defaults.update(kwargs)
    return field_class(**defaults)

  def has_default(self):
    return self.default is not NOT_PROVIDED


class KeyPropertyWrapper(PropertyWrapper):
  formfield_class = KeyField

  def __init__(self, *args, **kwargs):
    super(KeyPropertyWrapper, self).__init__(*args, **kwargs)
    self.is_relation = True
    # Although a repeated KeyProperty is really a M2M relation, we don't want to
    # set self.many_to_many or use ManyToManyRel as it triggers all kinds of
    # expectations on through models etc that aren't valid.
    self.many_to_one = True
    rel_class = ManyToOneRel
    remote_kind = ndb.Model._kind_map.get(self.property._kind)
    self.remote_field = rel_class(self, remote_kind, 'pk')
    self.related_model = remote_kind
    self.target_field = self.remote_field.get_related_field()
    if self.property._repeated:
      self.formfield_class = MultipleKeyField

  def formfield(self, **kwargs):
    defaults = {
      # 'required': self.property._required,
      'kind': self.property._kind
    }
    defaults.update(kwargs)
    return super(KeyPropertyWrapper, self).formfield(**defaults)

  def get_path_info(self):
    """
    Get path from this field to the related model.
    """
    opts = self.remote_field.model._meta
    from_opts = self.model._meta
    return [PathInfo(from_opts, opts, (self.remote_field,), self, False, True)]

  def get_choices(self, include_blank=True, blank_choice=BLANK_CHOICE_DASH,
                  limit_to_currently_related=False):
    """
    Return choices with a default blank choices included, for use as
    SelectField choices for this field.

    Analog of django.db.models.fields.Field.get_choices(), provided
    initially for utilization by RelatedFieldListFilter.
    """
    first_choice = blank_choice if include_blank else []
    queryset = ndb.Query(kind=self.property._kind)

    lst = [(x.key.urlsafe(), smart_text(x)) for x in queryset]
    return first_choice + lst

class StringPropertyWrapper(PropertyWrapper):
  pass

class IntegerPropertyWrapper(PropertyWrapper):
  formfield_class = forms.IntegerField

class BooleanPropertyWrapper(PropertyWrapper):
  formfield_class = forms.BooleanField
  def display_value(self, value):
    from django.contrib.admin.templatetags.admin_list import _boolean_icon
    return _boolean_icon(value)

class FloatPropertyWrapper(PropertyWrapper):
  formfield_class = forms.FloatField

class DatePropertyWrapper(PropertyWrapper):
  formfield_class = forms.DateField

class DateTimePropertyWrapper(PropertyWrapper):
  formfield_class = forms.DateTimeField

class TimePropertyWrapper(PropertyWrapper):
  formfield_class = forms.TimeField

class TextPropertyWrapper(PropertyWrapper):
  formfield_class = forms.CharField

  def formfield(self, **kwargs):
    defaults = {
      'widget': forms.Textarea
    }
    defaults.update(kwargs)
    super(KeyPropertyWrapper, self).formfield(**defaults)

WRAPPERS = {
  ndb.IntegerProperty: IntegerPropertyWrapper,
  ndb.BooleanProperty: BooleanPropertyWrapper,
  ndb.FloatProperty: FloatPropertyWrapper,
  ndb.DateProperty: DatePropertyWrapper,
  ndb.DateTimeProperty: DateTimePropertyWrapper,
  ndb.TextProperty: TextPropertyWrapper,
  ndb.KeyProperty: KeyPropertyWrapper,
}

class KeyWrapper(PropertyWrapper):
  def __init__(self, key):
    self.property_ = key
    self.attname = 'pk'
    self.name = 'key'
    self.editable = False
    self.unique = True
    self.rel = None
    self.primary_key = True
    self.auto_created = True
    self.remote_field = None
    self.default = NOT_PROVIDED
    # key is always the first field
    self.creation_counter = 0

  def to_python(self, value):
    if isinstance(value, basestring):
      return ndb.Key(urlsafe=value)
    return value


class InnerMeta:
  pass


class NdbMeta(options.Options):
  @classmethod
  def associate_to_model(cls, model, app_label):
    instance = cls(InnerMeta, app_label)
    instance.contribute_to_class(model, None)
    instance.add_field(KeyWrapper(instance.model.key))

    # ndb models store their properties in a standard dict, so there is no
    # consistent field order. The Django model metaclass registers fields with a
    # creation_counter attribute in the order they are defined; we can't do that
    # without hacking the ndb code itself. The best alternative is to support
    # an optional 'field_order' attribute on the model which allows the user
    # to specify fields in a particular order, which will be used to set the
    # creation_counter. If the field_order attribute is missing, or does not
    # contain all the defined fields, they will be added in sorted order.
    field_order = getattr(model, 'field_order', None)
    all_fields = instance.model._properties
    if field_order:
      # check we have all the fields listed; if not, just add them on the end.
      missing = set(all_fields).difference(field_order)
      if missing:
        field_order.extend(sorted(missing))
    else:
      field_order = sorted(all_fields)
    for creation_counter, fieldname in enumerate(field_order):
      field = all_fields[fieldname]
      wrapper_class = WRAPPERS.get(field.__class__, PropertyWrapper)
      wrapper = wrapper_class(fieldname, field, model, creation_counter)
      instance.add_field(wrapper)


class NdbModelMeta(ndb.MetaModel):
  def __init__(cls, name, bases, attrs):
    super(NdbModelMeta, cls).__init__(name, bases, attrs)
    NdbMeta.associate_to_model(cls, 'meta')


class KeyValue(object):
  def __init__(self, value):
    self.value = value

  @property
  def pk(self):
    return self.value

  def __unicode__(self):
    return self.value.urlsafe()

  def __hash__(self):
    return hash(self.value)

  def __eq__(self, other):
    if isinstance(other, ndb.Key):
      return self.value == other
    elif isinstance(other, KeyValue):
      return self.value == other.value
    else:
      return False


class DjangoCompatibleModel(ndb.Model):
  __metaclass__ = NdbModelMeta

  def __init__(self, *args, **kwargs):
    super(DjangoCompatibleModel, self).__init__(*args, **kwargs)
    self._state = ModelState()

  def validate_unique(self, *args, **kwargs):
    pass

  def _get_unique_checks(self, exclude=None):
    return [(),()]

  def full_clean(self, *args, **kwargs):
    pass

  def save(self, *args, **kwargs):
    self.put()

  def delete(self, *args, **kwargs):
    self.key.delete()

  @property
  def pk(self):
    if self.key:
      return KeyValue(self.key)

  def serializable_value(self, prop):
    if prop in ['pk', 'id', 'key']:
      return self.key.urlsafe()
    return self._values[prop]


class User(DjangoCompatibleModel):
  user_id = ndb.StringProperty()
  username = ndb.StringProperty()
  email = ndb.StringProperty()
  is_staff = ndb.BooleanProperty(default=False)


  def __unicode__(self):
    return self.username
