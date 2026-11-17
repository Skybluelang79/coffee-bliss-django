from django.urls import path

from . import views

app_name = "assistant"

urlpatterns = [
    path("chat/", views.customer_chat, name="customer_chat"),
    path("chat/reset/", views.customer_reset, name="customer_reset"),
    path("staff/chat/", views.staff_chat, name="staff_chat"),
    path("staff/chat/reset/", views.staff_reset, name="staff_reset"),
]
