from django.urls import path

from . import views

app_name = "moderation"
urlpatterns = [
    path(
        "reviews/<uuid:review_id>/audits/adjudicate/<uuid:submission_id>/<str:criterion>/",
        views.adjudicate_audit,
        name="adjudicate_audit",
    ),
    path("", views.index, name="index"),
    path("reviews/<uuid:review_id>/", views.review, name="review"),
    path(
        "reviews/<uuid:review_id>/audits/",
        views.validation_list,
        name="validation_list",
    ),
    path(
        "reviews/<uuid:review_id>/audits/compare/",
        views.validation_comparison,
        name="validation_comparison",
    ),
    path(
        "reviews/<uuid:review_id>/audits/approve/<str:criterion>/",
        views.approve_check,
        name="approve_check",
    ),
    path(
        "reviews/<uuid:review_id>/process/", views.review_process, name="review_process"
    ),
    path(
        "reviews/<uuid:review_id>/study-settings/",
        views.study_settings,
        name="study_settings",
    ),
    path(
        "reviews/<uuid:review_id>/<uuid:submission_id>/audit/",
        views.validation_audit,
        name="validation_audit",
    ),
    path("reviews/<uuid:review_id>/progress/", views.progress, name="progress"),
    path("reviews/<uuid:review_id>/resume/", views.resume, name="resume"),
    path(
        "reviews/<uuid:review_id>/attempts/",
        views.attempt_selection,
        name="attempt_selection",
    ),
    path(
        "reviews/<uuid:review_id>/feedback/", views.bulk_feedback, name="bulk_feedback"
    ),
    path(
        "reviews/<uuid:review_id>/feedback/download/",
        views.download_feedback,
        name="download_feedback",
    ),
    path("reviews/<uuid:review_id>/export/<str:kind>/", views.export, name="export"),
    path(
        "reviews/<uuid:review_id>/<uuid:submission_id>/",
        views.submission,
        name="submission",
    ),
    path(
        "reviews/<uuid:review_id>/<uuid:submission_id>/feedback/",
        views.feedback,
        name="feedback",
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
