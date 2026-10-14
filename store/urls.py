from django.urls import path

from . import views

app_name = "store"

urlpatterns = [
    path("", views.home, name="home"),
    path("menu/", views.menu, name="menu"),
    path("categories/", views.categories, name="categories"),
    path("product/<slug:slug>/", views.product_detail, name="product_detail"),
    path("product/<slug:slug>/review/", views.add_review, name="add_review"),
    path("product/<slug:slug>/favorite/", views.toggle_favorite, name="toggle_favorite"),
    path("locations/", views.locations, name="locations"),
    path("subscriptions/", views.subscriptions, name="subscriptions"),
    path("blog/", views.blog, name="blog"),
    path("blog/<slug:slug>/", views.blog_detail, name="blog_detail"),
    path("about/", views.about, name="about"),
    path("contact/", views.contact, name="contact"),
    path("newsletter/", views.subscribe, name="subscribe"),
]
