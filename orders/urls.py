from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("", views.OrderListView.as_view(), name="list"),
    path("create/", views.OrderCreateView.as_view(), name="create"),
    path("<int:pk>/", views.OrderDetailView.as_view(), name="detail"),
    path("<int:pk>/items/add/", views.OrderItemCreateView.as_view(), name="item_add"),
    path("items/<int:pk>/edit/", views.OrderItemUpdateView.as_view(), name="item_update"),
    path("items/<int:pk>/delete/", views.OrderItemDeleteView.as_view(), name="item_delete"),
    path("<int:pk>/status/", views.OrderStatusUpdateView.as_view(), name="status"),
    path("export/", views.OrderExportView.as_view(), name="export"),
]
