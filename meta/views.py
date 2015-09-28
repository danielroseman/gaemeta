from django import forms
from django.shortcuts import render, redirect
from meta.models import Book

# Create your views here.

def books(request):
  return render(request, 'books.html', {'books': Book.query()})

def create_book(request, name):
  book = Book(name=name)
  book.put()
  return redirect('/books/')

class BookForm(forms.ModelForm):
  class Meta:
    model = Book
    fields = ('name',  'pages')

def book_form(request, name):
  book = Book.query(Book.name==name).get()
  if request.method == 'POST':
    form = BookForm(request.POST, instance=book)
    if form.is_valid():
      form.save()
      return redirect('/books/')
  else:
    form = BookForm(instance=book)
  return render(request, 'book_form.html', {'form': form})

