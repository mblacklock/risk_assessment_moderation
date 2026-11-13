from django.urls import path

from . import views

app_name = "moderation"
urlpatterns = [
    path("", views.index, name="index"),
    path("reviews/<uuid:review_id>/", views.review, name="review"),
    path("reviews/<uuid:review_id>/progress/", views.progress, name="progress"),
    path("reviews/<uuid:review_id>/resume/", views.resume, name="resume"),
    path("reviews/<uuid:review_id>/export/<str:kind>/", views.export, name="export"),
    path(
        "reviews/<uuid:review_id>/<uuid:submission_id>/",
        views.submission,
        name="submission",
    ),
    path(
        "reviews/<uuid:review_id>/<uuid:submission_id>/checks/<str:criterion>/",
        views.decide,
        name="decide",
    ),
    path(
        "reviews/<uuid:review_id>/<uuid:submission_id>/files/<uuid:file_id>/",
        views.download,
        name="download",
    ),
    path(
        "reviews/<uuid:review_id>/<uuid:submission_id>/images/<int:doc_index>/<int:image_index>/",
        views.image,
        name="image",
    ),
]
