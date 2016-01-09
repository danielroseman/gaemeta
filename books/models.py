from __future__ import unicode_literals
from google.appengine.ext import ndb
from meta.models import DjangoCompatibleModel

class Author(DjangoCompatibleModel):
  name = ndb.StringProperty()
  sex = ndb.StringProperty(choices=('Male', 'Female'))
  alive = ndb.BooleanProperty()

  class Meta:
    field_order = ['name', 'sex', 'alive']

  def __unicode__(self):
    return self.name


class Book(DjangoCompatibleModel):
  name = ndb.StringProperty()
  author = ndb.KeyProperty(Author)
  pages = ndb.IntegerProperty(default=100)
  read = ndb.DateProperty()

  class Meta:
    field_order = ['name', 'author', 'pages']

  def __unicode__(self):
    return self.name
