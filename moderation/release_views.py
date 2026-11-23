"""Small operational UI; uses raw saved sources, never jobs.snapshot."""

from django import forms
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from . import release, release_bulk, release_store, store


class SetupForm(forms.Form):
    cohort = forms.ChoiceField(label="Cohort roster (selected latest attempts)")
    sources = forms.MultipleChoiceField(
        label="Existing assessment batches", widget=forms.CheckboxSelectMultiple
    )
    supplemental = forms.MultipleChoiceField(
        label="Additional saved moderation decisions",
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, reviews, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [(r["id"], r["title"]) for r in reviews]
        for field in self.fields.values():
            field.choices = choices


class ReleaseForm(forms.Form):
    revision = forms.CharField(widget=forms.HiddenInput)
    source_token = forms.CharField(widget=forms.HiddenInput)
    outcome = forms.ChoiceField(
        label="Final outcome",
        choices=[("", "Choose an outcome"), *release.OUTCOMES.items()],
        required=False,
    )
    student_corrections = forms.CharField(
        label="Required student corrections",
        required=False,
        max_length=18000,
        widget=forms.Textarea(attrs={"rows": 5}),
    )
    supervisor_completion = forms.CharField(
        label="Required supervisor completion",
        required=False,
        max_length=18000,
        widget=forms.Textarea(attrs={"rows": 4}),
    )
    supervisor_followup = forms.CharField(
        label="Supervisor follow-up (not required for resubmission)",
        required=False,
        max_length=18000,
        widget=forms.Textarea(attrs={"rows": 4}),
    )
    moderator = forms.CharField(
        label="Responsible moderator", required=False, max_length=200
    )
    original_moderator_feedback = forms.CharField(
        label="Original moderator feedback (private; not exported)",
        required=False,
        max_length=50000,
        widget=forms.Textarea(attrs={"rows": 5}),
    )
    resolution = forms.CharField(
        label="Decision / waiver resolution (private; not exported)",
        required=False,
        max_length=10000,
        widget=forms.Textarea(attrs={"rows": 4}),
    )
    resolve = forms.BooleanField(
        label="I have resolved the listed ambiguities, conflicts and waivers in the final result and wording.",
        required=False,
    )
    confirm = forms.BooleanField(
        label="I explicitly confirm this final outcome and student-facing feedback for release.",
        required=False,
    )
    replace = forms.BooleanField(
        label="I explicitly authorise replacing the existing finalised record. Its previous version will remain in history.",
        required=False,
    )


def load_state():
    register = release_store.load()
    if not register:
        return None, {}
    return register, release.source_state(register)


@never_cache
@require_http_methods(["GET", "POST"])
def index(request):
    try:
        register = release_store.load()
        if not register:
            reviews = store.list_reviews()
            defaults = {
                "cohort": next(
                    (r["id"] for r in reviews if r["title"] == "All v2"), ""
                ),
                "sources": [
                    r["id"]
                    for r in reviews
                    if r["title"] in {f"Sample {i}" for i in range(1, 6)}
                    or "Validation" in r["title"]
                ],
                "supplemental": [r["id"] for r in reviews if r["title"] == "All"],
            }
            form = SetupForm(
                reviews,
                request.POST if request.method == "POST" else None,
                initial=defaults,
            )
            if request.method == "POST" and form.is_valid():
                try:
                    release.create(
                        form.cleaned_data["cohort"],
                        form.cleaned_data["sources"],
                        form.cleaned_data["supplemental"],
                    )
                except ValueError as error:
                    form.add_error(None, str(error))
                else:
                    return redirect("moderation:release_index")
            return render(request, "moderation/release_setup.html", {"form": form})
        bundles = release.source_state(register)
        bulk_state = release_bulk.overview(
            register, bundles, request.GET.get("scope", "existing")
        )
    except (ValueError, OSError, KeyError) as error:
        return render(
            request, "moderation/release_error.html", {"error": str(error)}, status=409
        )
    rows = []
    readiness_rows = {r["number"]: r for r in bulk_state["rows"]}
    for number, record in register["records"].items():
        if number not in readiness_rows:
            continue
        bundle = bundles[number]
        readiness = readiness_rows[number]
        changed = release.source_changed(record, bundle)
        valid = release.release_valid(record, bundle)
        proposal = record.get("refreshed_proposal") or record["proposal"]
        issues = list(proposal.get("decision_gaps", proposal["issues"]))
        if changed:
            issues.insert(0, "Source evidence changed; review before release.")
        if valid:
            issues = []
        academic = changed or bool(proposal.get("decision_gaps", []))

        rows.append(
            {
                **record,
                "readiness": readiness["readiness"],
                "bulk_reasons": readiness["reasons"],
                "edited_draft": readiness["edited"],
                "valid": valid,
                "source_changed": changed,
                "issues": issues,
                "academic_decision": academic,
                "outcome_label": release.OUTCOMES.get(
                    record["outcome"], "Decision required"
                ),
                "status_label": "Finalised"
                if valid
                else "Source changed — review required"
                if changed
                else "Awaiting moderator feedback"
                if record["status"] == "awaiting_feedback"
                else "Decision required"
                if academic
                else "Wording confirmation required"
                if issues
                else "Feedback ready to review — not finalised",
            }
        )
    counts = {
        "total": len(rows),
        "sourced": sum(bool(b["sources"]) for b in bundles.values()),
        "proposed": sum(bool(r["outcome"]) for r in rows),
        "unresolved": sum(
            bool(r["issues"]) and r["status"] != "awaiting_feedback" for r in rows
        ),
        "awaiting": sum(r["status"] == "awaiting_feedback" for r in rows),
        "finalised": sum(r["valid"] for r in rows),
        "academic": sum(r["academic_decision"] for r in rows),
        "reconstructed": sum(
            bool(bundles[r["number"]]["sources"]) and not r["academic_decision"]
            for r in rows
        ),
    }
    query = request.GET.get("q", "").strip().casefold()
    status = request.GET.get("status", "")
    readiness_filter = request.GET.get("readiness", "")
    outcome_filter = request.GET.get("outcome", "")
    batch_filter = request.GET.get("batch", "")
    rows = [
        r
        for r in rows
        if (
            not query
            or query
            in (r["number"] + " " + r["name"] + " " + r["source_batch"]).casefold()
        )
        and (
            not status
            or (status == "finalised" and r["valid"])
            or (status == "unfinalised" and not r["valid"])
            or (status == "decision" and r["issues"])
            or (status == "awaiting" and r["status"] == "awaiting_feedback")
        )
        and (not readiness_filter or r["readiness"] == readiness_filter)
        and (not outcome_filter or r["outcome"] == outcome_filter)
        and (not batch_filter or r["source_batch"] == batch_filter)
    ]
    sort = request.GET.get("sort", "name")
    if sort not in {"number", "name", "source_batch", "outcome_label", "status_label"}:
        sort = "name"
    descending = request.GET.get("direction") == "desc"
    rows.sort(key=lambda r: (r[sort].casefold(), r["number"]), reverse=descending)
    return render(
        request,
        "moderation/release_index.html",
        {
            "register": register,
            "rows": rows,
            "counts": counts,
            "q": request.GET.get("q", ""),
            "status": status,
            "sort": sort,
            "direction": "desc" if descending else "asc",
            "saved": request.GET.get("saved") == "1",
            "bulk": bulk_state,
            "readiness_filter": readiness_filter,
            "outcome_filter": outcome_filter,
            "batch_filter": batch_filter,
            "batch_options": sorted({r["source_batch"] for r in bulk_state["rows"]}),
        },
    )


@never_cache
@require_http_methods(["GET", "POST"])
def editor(request, number):
    try:
        register, bundles = load_state()
        if not register:
            return redirect("moderation:release_index")
        if number not in register["records"]:
            raise Http404("Student is not in the release roster.")
        record = register["records"][number]
        bundle = bundles[number]
    except (ValueError, OSError, KeyError) as error:
        return render(
            request, "moderation/release_error.html", {"error": str(error)}, status=409
        )
    token = release.digest(bundle)
    initial = {**record, "revision": register["revision"], "source_token": token}
    if not initial.get("moderator"):
        initial["moderator"] = register.get("last_finaliser", "")
    form = ReleaseForm(
        request.POST if request.method == "POST" else None, initial=initial
    )
    preview = (
        record["final_text"]
        if release.release_valid(record, bundle)
        else release.format_feedback(record)
    )
    if request.method == "POST" and form.is_valid():
        values = form.cleaned_data
        preview = release.format_feedback(values)
        if request.POST.get("action") != "preview":
            try:
                release.save_record(
                    values["revision"],
                    number,
                    values,
                    finalise=request.POST.get("action") == "finalise",
                    confirm=values["confirm"],
                    replace=values["replace"],
                    resolve=values["resolve"],
                    source_token=values["source_token"],
                )
            except (ValueError, OSError, KeyError) as error:
                form.add_error(None, str(error))
            else:
                return redirect(reverse("moderation:release_index") + "?saved=1")
    references = []
    for source in bundle["sources"] + bundle["supplemental"]:
        audit = (source["validation_audits"] or [{}])[-1]
        references.append(
            {
                "batch": source["batch"],
                "submitted": source["submitted"],
                "id": source["submission_id"],
                "reviewer": audit.get("reviewer", ""),
                "notes": audit.get("notes", ""),
                "other": audit.get("other_corrections", ""),
                "checks": source["checks"],
                "adjudications": source["audit_adjudications"],
                "historical": source["historical_adjudications"],
                "feedback": source["elp_feedback"],
                "manual": source.get("manual_moderation", {}),
                "conversation": source.get("conversation_decisions", {}),
                "batch_acceptance": register.get(
                    "conversation_batch_acceptances", {}
                ).get(source["review_id"], {}),
                "files": source["files"],
                "matches": release.same_attempt(source, bundle["roster"]),
            }
        )
    proposal = release.propose(bundle)
    issues = list(proposal.get("decision_gaps", proposal["issues"]))
    if release.source_changed(record, bundle):
        from .release_sources import change_summary

        issues = change_summary(record, bundle) + issues
    response = render(
        request,
        "moderation/release_editor.html",
        {
            "record": record,
            "form": form,
            "preview": preview,
            "issues": issues,
            "references": references,
            "history": list(reversed(record["history"])),
            "refreshed": record.get("refreshed_proposal"),
            "valid": release.release_valid(record, bundle),
            "preview_unsaved": request.method == "POST",
            "wording_gaps": proposal.get("wording_gaps", []),
            "has_sources": bool(bundle["sources"]),
            "manual_sources": [
                s.get("manual_moderation")
                for s in bundle["sources"]
                if s.get("manual_moderation")
            ],
        },
    )
    response["Cache-Control"] = "no-store"
    return response


@require_POST
def refresh(request):
    try:
        release.refresh(request.POST.get("revision", ""))
    except (ValueError, OSError, KeyError) as error:
        return render(
            request, "moderation/release_error.html", {"error": str(error)}, status=409
        )
    return redirect("moderation:release_index")


@never_cache
@require_GET
def export(request):
    try:
        register, bundles = load_state()
        if not register:
            return redirect("moderation:release_index")
        payload = release.export_xlsx(
            register, bundles, request.GET.get("finalised_only") == "1"
        )
    except (ValueError, OSError, KeyError) as error:
        return render(
            request, "moderation/release_error.html", {"error": str(error)}, status=409
        )
    response = HttpResponse(
        payload,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = (
        'attachment; filename="KB6060-student-feedback.xlsx"'
    )
    response["Cache-Control"] = "no-store"
    return response
