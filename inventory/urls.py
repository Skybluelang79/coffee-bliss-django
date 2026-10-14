from django.urls import path

from . import views

app_name = "inventory"

urlpatterns = [
    path("", views.inventory_home, name="home"),
    path("new/", views.ingredient_create, name="create"),
    path("movements/", views.movements, name="movements"),
    path("recipes/", views.recipe_list, name="recipes"),
    path("recipes/<slug:slug>/", views.recipe_edit, name="recipe_edit"),
    path("recipes/<slug:slug>/items/<int:pk>/delete/", views.recipe_delete, name="recipe_delete"),
    path("<int:pk>/", views.ingredient_detail, name="detail"),
    path("<int:pk>/edit/", views.ingredient_edit, name="edit"),
    path("<int:pk>/restock/", views.ingredient_restock, name="restock"),
    path("<int:pk>/adjust/", views.ingredient_adjust, name="adjust"),
    path("<int:pk>/waste/", views.ingredient_waste, name="waste"),
]
