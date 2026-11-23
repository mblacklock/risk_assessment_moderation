"""Cohort preview and explicit approval; GET requests never finalise feedback."""

from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from . import release, release_bulk, release_store


@never_cache
@require_http_methods(["GET", "POST"])
def preview(request):
    result, error = None, ""
    try:
        register = release_store.load()
        if not register:
            return redirect("moderation:release_index")
        scope = (
            request.POST.get("scope", "existing")
            if request.method == "POST"
            else request.GET.get("scope", "existing")
        )
        if request.method == "POST":
            token = request.POST.get("preview_token", "")
            manifest = release_bulk.load_manifest(token)
            scope = manifest["scope"]
            if request.POST.get("action") == "download":
                if manifest["register"] != register["id"]:
                    raise ValueError("The register changed. Open a fresh preview.")
                state = release_bulk.overview(
                    register, release.source_state(register), scope
                )
                eligible = {r["number"]: r for r in state["ready"]}
                if any(
                    n not in eligible or eligible[n]["token"] != expected
                    for n, expected in manifest["records"].items()
                ):
                    raise ValueError(
                        "Feedback changed since the preview. Open a fresh preview before downloading."
                    )
                rows = [eligible[n] for n in manifest["records"]]
                response = HttpResponse(
                    release_bulk.review_xlsx(rows),
                    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
                response["Content-Disposition"] = (
                    'attachment; filename="KB6060-feedback-review-NOT-FINALISED.xlsx"'
                )
                response["Cache-Control"] = "no-store"
                return response
            if request.POST.get("action") != "finalise":
                raise ValueError(
                    "Choose preview download or explicit bulk finalisation."
                )
            result = release_bulk.finalise(
                token,
                request.POST.get("moderator", ""),
                confirm=request.POST.get("confirm") == "on",
                confirm_edits=request.POST.get("confirm_edits") == "on",
            )
            register = release_store.load()
        state = release_bulk.overview(register, release.source_state(register), scope)
    except (ValueError, OSError, KeyError) as problem:
        error = str(problem)
        try:
            register = release_store.load()
            if not register:
                raise ValueError("Create the feedback register first.")
            scope = (
                request.POST.get("scope", "existing")
                if request.method == "POST"
                else "existing"
            )
            state = release_bulk.overview(
                register, release.source_state(register), scope
            )
        except (ValueError, OSError, KeyError) as failure:
            return render(
                request,
                "moderation/release_error.html",
                {"error": str(failure)},
                status=409,
            )
    response = render(
        request,
        "moderation/release_bulk.html",
        {
            "bulk": state,
            "preview_token": release_bulk.preview_manifest(register, state),
            "moderator": request.POST.get(
                "moderator", register.get("last_finaliser", "")
            ),
            "error": error,
            "result": result,
        },
        status=409 if error else 200,
    )
    response["Cache-Control"] = "no-store"
    return response
