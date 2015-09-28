from django.conf.urls import include, url
#from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from meta import views, admin

urlpatterns = [
    # Examples:
    # url(r'^$', 'gaemeta.views.home', name='home'),
    # url(r'^blog/', include('blog.urls')),
    url(r'^books/$', views.books, name="books"),
    url(r'^create_book/(?P<name>\w+)/$', views.create_book, name="create_book"),
    url(r'book_form/(?P<name>[\w ]+)/$', views.book_form, name="book_form"),

    url(r'^admin/', include(admin.site.urls)),
]  + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

