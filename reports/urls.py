from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("search/", views.SearchView.as_view(), name="search"),
    path("statistics/", views.StatisticsView.as_view(), name="statistics"),
    path("logs/", views.LogListView.as_view(), name="logs"),
    path("export/", views.ExportView.as_view(), name="export"),
    path("print/", views.PrintView.as_view(), name="print"),
]
