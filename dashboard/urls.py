from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("staff/", views.staff_home, name="staff_home"),
    path("staff/kds/", views.staff_kds, name="staff_kds"),
    path("staff/orders/", views.staff_orders, name="staff_orders"),
    path("staff/orders/<str:number>/status/", views.staff_update_status, name="staff_update_status"),
    path("staff/reservations/", views.staff_reservations, name="staff_reservations"),
    path("staff/reservations/<int:pk>/", views.staff_update_reservation, name="staff_update_reservation"),
    path("admin/", views.admin_home, name="admin_home"),
    path("admin/customers/", views.customers, name="customers"),
    path("admin/customers/<int:pk>/", views.customer_detail, name="customer_detail"),
    path("admin/reports/", views.reports, name="reports"),
    path("admin/cart-reminders/send/", views.send_cart_reminders, name="send_cart_reminders"),
]
