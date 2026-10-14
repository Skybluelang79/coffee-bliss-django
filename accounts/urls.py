from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.CoffeeLoginView.as_view(), name="login"),
    path("signup/", views.signup_view, name="signup"),
    path("logout/", views.logout_view, name="logout"),
    path("", views.dashboard, name="dashboard"),
    path("profile/", views.profile_view, name="profile"),
    path("password/", views.CoffeePasswordChangeView.as_view(), name="password_change"),
    path("addresses/", views.address_list, name="addresses"),
    path("addresses/<int:pk>/delete/", views.address_delete, name="address_delete"),
    path("orders/<str:number>/", views.order_detail, name="order_detail"),
]
