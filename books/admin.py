from meta.admin import site, NdbAdmin, TabularNdbInline
from books.models import Book, Author, Library
from django.contrib import admin

class BookInline(TabularNdbInline):
  model = Book

class AuthorAdmin(NdbAdmin):
  model = Author
  inlines = [BookInline]
  list_display = ('name', 'sex', 'alive')
  list_filter = ('sex', 'alive')
  # radio_fields = {'sex': admin.HORIZONTAL}

class BookAdmin(NdbAdmin):
  model = Book
  list_display = ('name', 'author', 'get_author', 'pages', 'read')
  list_filter = ('author', 'read')
  radio_fields = {'author': admin.HORIZONTAL}
  #raw_id_fields = ('author',)
  # list_editable = ('pages',)

  def get_author(self, obj):
    return obj.author.get() if obj.author else ""
  get_author.short_description = 'Author'


class LibraryAdmin(NdbAdmin):
  model = Library
  raw_id_fields = ('books',)
  #filter_horizontal = ('books',)


site.register(Book, BookAdmin)
site.register(Author, AuthorAdmin)
site.register(Library, LibraryAdmin)
