from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("cart/", views.cart_detail, name="cart"),
    path("cart/add/<int:product_id>/", views.cart_add, name="cart_add"),
    path("cart/update/<int:product_id>/", views.cart_update, name="cart_update"),
    path("cart/remove/<int:product_id>/", views.cart_remove, name="cart_remove"),
    path("cart/coupon/", views.apply_coupon, name="apply_coupon"),
    path("cart/gift-card/", views.apply_gift_card, name="apply_gift_card"),
    path("cart/gift-card/remove/", views.remove_gift_card, name="remove_gift_card"),
    path("cart/email/", views.capture_cart_email, name="capture_cart_email"),
    path("checkout/", views.checkout, name="checkout"),
    path("payment/<str:number>/", views.payment_page, name="payment"),
    path("payment/<str:number>/simulate/", views.payment_simulate, name="payment_simulate"),
    path("payment/<str:number>/paystack/", views.paystack_initialize, name="paystack_initialize"),
    path("payment/<str:number>/paystack/callback/", views.paystack_callback, name="paystack_callback"),
    path("stripe/webhook/", views.stripe_webhook, name="stripe_webhook"),
    path("paystack/webhook/", views.paystack_webhook, name="paystack_webhook"),
    path("confirmation/<str:number>/", views.order_confirmation, name="order_confirmation"),
    path("track/", views.track_lookup, name="track_lookup"),
    path("track/<str:number>/", views.track_order, name="track"),
    path("track/<str:number>/status.json", views.track_status, name="track_status"),
    path("track/<str:number>/cancel/", views.cancel_order, name="cancel"),
    path("track/<str:number>/reorder/", views.reorder, name="reorder"),
    path("track/<str:number>/receipt/", views.receipt, name="receipt"),
    path("track/<str:number>/rate/", views.rate_order, name="rate"),
    path("track/<str:number>/notify/", views.toggle_notifications, name="toggle_notifications"),
    path("notify/", views.notify_pref, name="notify_pref"),
    path("history/", views.order_history, name="history"),
    path("reserve/", views.reserve, name="reserve"),
    path("reserve/success/<int:pk>/", views.reservation_success, name="reservation_success"),
]
