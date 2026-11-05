from django.urls import path

from . import views

app_name = "appointments"

urlpatterns = [
    path("", views.AppointmentListView.as_view(), name="list"),
    path("create/", views.AppointmentCreateView.as_view(), name="create"),
    path("<int:pk>/", views.AppointmentDetailView.as_view(), name="detail"),
    path("<int:pk>/transition/", views.AppointmentTransitionView.as_view(), name="transition"),
    path("<int:pk>/note/", views.AppointmentNoteView.as_view(), name="note"),
    path("<int:pk>/attachment/upload/", views.AppointmentAttachmentUploadView.as_view(),
         name="attachment_upload"),
    path("attachment/<int:pk>/delete/", views.AppointmentAttachmentDeleteView.as_view(),
         name="attachment_delete"),
    path("export/", views.AppointmentExportView.as_view(), name="export"),
]
