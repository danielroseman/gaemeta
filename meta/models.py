from django.apps import apps
from django.db import models
from django.db.models import options
from django.db.models.base import ModelState
from django.db.models.fields.related import ManyToManyRel, ManyToOneRel
from django import forms
from django.utils.functional import cached_property
from django.utils.text import capfirst

from google.appengine.ext import ndb

from meta.forms import KeyField

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

  def __init__(self, name, property_, model):
    self.name = name
    self.property = property_
    self.model = model
    self.blank = not self.property._required
    self.default = getattr(self.property, 'default', None)
    self.flatchoices = self.choices = [(x, x) for x in property_._choices or []]
    self.verbose_name = property_._verbose_name or name
    if isinstance(self.property, ndb.KeyProperty):
      self.is_relation = True
      if getattr(self.property, 'repeated', False):
        self.many_to_many = True
        rel_class = ManyToManyRel
      else:
        self.many_to_one = True
        rel_class = ManyToOneRel
      self.remote_field = rel_class(self, ndb.Model._kind_map.get(self.property._kind), 'key')
    else:
      self.remote_field = None

  def __repr__(self):
    return 'PropertyWrapper: {}'.format(self.name)

  #@cached_property
  #def related_model(self):
    #return self.remote_field.model

  def get_attname(self):
    return self.name

  def get_flatchoices(self, include_blank, blank_choice):
    return self.choices

  def value_from_object(self, obj):
    value = getattr(obj, self.name)
    if isinstance(value, ndb.Key):
      value = value.urlsafe()
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
      # ndb default must be a value, not a callable
      defaults['initial'] = self.default
    if self.choices:
      defaults['choices'] = self.choices
      field_class = forms.ChoiceField
    elif isinstance(self.property, ndb.KeyProperty):
      defaults['required'] = self.property._required
      defaults['kind'] = self.property._kind
      field_class = KeyField
    else:
      fields = {
        ndb.StringProperty: forms.CharField,
        ndb.IntegerProperty: forms.IntegerField,
        ndb.BooleanProperty: forms.BooleanField,
      }
      field_class = fields[self.property.__class__]
    defaults.update(kwargs)
    return field_class(**defaults)


class KeyWrapper(PropertyWrapper):
  def __init__(self, key):
    self.property_ = key
    self.attname = 'id'
    self.name = 'key'
    self.editable = False
    self.unique = True
    self.rel = None
    self.primary_key = True
    self.auto_created = True
    self.remote_field = None

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
    # consistent field order - unlike Django, which uses an OrderedDict. There
    # isn't anything we can do about this without hacking the ndb code itself;
    # the best alternative is to allow an optional 'field_order' attribute on
    # the model which allows the user to specify fields in a particular order.
    # If the attribute is missing, or does not contain all the defined fields,
    # they will be added in sorted order.
    field_order = getattr(model, 'field_order', None)
    all_fields = instance.model._properties
    if field_order:
      # check we have all the fields listed; if not, just add them on the end.
      missing = set(all_fields).difference(field_order)
      if missing:
        field_order.extend(sorted(missing))
    else:
      field_order = sorted(all_fields)
    for fieldname in field_order:
      wrapper = PropertyWrapper(fieldname, all_fields[fieldname], model)
      instance.add_field(wrapper)


class NdbModelMeta(ndb.MetaModel):
  def __init__(cls, name, bases, attrs):
    super(NdbModelMeta, cls).__init__(name, bases, attrs)
    NdbMeta.associate_to_model(cls, 'meta')


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
  def id(self):
    if self.key:
      return self.key.urlsafe()

  @property
  def pk(self):
    return self.key
    #if self.key:
      #return self.key.urlsafe()

  def serializable_value(self, prop):
    if prop in ['pk', 'id']:
      return self.key.urlsafe()
    return self._values[prop]


class Author(DjangoCompatibleModel):
  name = ndb.StringProperty()
  sex = ndb.StringProperty(choices=('Male', 'Female'))

  def __unicode__(self):
    return self.name


class Book(DjangoCompatibleModel):
  name = ndb.StringProperty()
  author = ndb.KeyProperty(Author)
  pages = ndb.IntegerProperty()

  field_order = ['name', 'author', 'pages']

  def __unicode__(self):
    return self.name
    #return u'{} by {}'.format(self.name, self.author.get())


class User(DjangoCompatibleModel):
  user_id = ndb.StringProperty()
  username = ndb.StringProperty()
  email = ndb.StringProperty()
  is_staff = ndb.BooleanProperty(default=False)


  def __unicode__(self):
    return self.username

