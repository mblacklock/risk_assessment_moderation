# Risk assessment moderation

## Student feedback release

Open **Student feedback release** in the main navigation. The cohort workflow is:
**Review exceptions → Preview cohort feedback → Bulk finalise → Export to eLP.**
Individual wording edits and finalisation remain available when needed.
This separate local register records intended feedback; nothing is uploaded or sent
into eLP automatically.

**Feedback-only exclusion:** Administrative questions are omitted from student-facing
feedback and its Pass/Fail calculation. The administrative checks, moderation grid,
saved judgements, validation statistics and histories are unchanged. A submission
whose only correction is administrative therefore receives Pass in its feedback,
while the original moderation outcome remains available internally. The exclusion
also applies to individual/bulk eLP feedback; other edited wording is preserved.
Previously finalised feedback prepared under an older exclusion policy is held for
explicit review rather than silently replaced or exported with outdated content.

The 106 selected latest attempts in **All v2** supply the roster. Samples 1–5 and
Validation v1/v2 supply the existing 65 assessments; the remaining 41 roster rows
retain the independent moderators' manual-entry route. No submissions are processed
again to reconstruct feedback, and no checking or AI is run.

### Recovering completed moderation

- Samples use saved operational decisions and overrides first, including matching
  decisions from the older All batch and preserved decision history. A later
  independent pilot audit does not silently replace saved operational moderation.
- Routine moderation also reuses validated automatic findings under the main
  moderation page's exact approval and checking-version policy. These remain
  labelled as automatic acceptance, not individual human review. Withdrawn or
  mismatched approvals restore the release hold. Independent validation findings,
  explicit staff decisions and waivers retain precedence.
- Validation records use original staff audits together with subsequent agreed
  interpretations. Unrelated audit revisions do not discard earlier agreements;
  explicit later edits to the relevant criterion are recognised.
- Linked original manual moderation workbooks provide recorded Pass/Fail outcomes,
  written comments and specific correction details. They are read-only sources,
  identified by path, sheet, row and file fingerprint in the private register. An
  operational Pass is not turned into Fail merely because an independent technical
  rubric marks a minor defect. Later explicit agreed correction judgements and
  recorded waivers are retained separately; no new waiver is inferred.
- An automatic Manual check/referral is distinct from the staff judgement. It does
  not reopen a definite human outcome. Technical routing and superseded findings
  remain in the optional source panel.
- Previously edited public wording is reused where consistent with the recorded
  final judgement. A stale checksum or format alone does not require repeating
  moderation. Original texts and all histories are preserved.
- Controlled instructions replace parser language, consolidate duplicate location
  corrections, separate missing supervisor completion from follow-up that is not required for resubmission,
  and retain relevant additional written requirements. Private comments, research
  annotations, raw AI explanations and source quotations are not copied into the
  public output.

Only genuinely absent or contradictory final judgements appear as saved-decision
gaps. Missing public wording is classified separately and does not become a new
academic decision. Where a final decision was not persisted, the record identifies
that specific missing decision; it does not claim the submission was never reviewed
or require the moderator to revisit 24 criteria.

Dated decisions recovered from an earlier conversation can be linked in the private
release register, with the transcript reference and the matching submission timestamp
and attachment hashes. They participate in the same chronology as other recorded
judgements; later agreed decisions supersede them. The original audits and review
files are not rewritten. Batch acceptance is retained as supporting history and is
not a blanket Pass or a resolution of ambiguous individual findings. Recovered public
instructions are explicitly separate from private transcript quotations.

The release preparation command refreshes untouched machine-prepared proposals
with recovered decisions and generated text. It never overwrites a staff-edited
draft or finalised feedback: refreshed proposals remain separately available for
those records. Existing submissions, decisions, audits, approvals and evaluation
histories stay unchanged.

### Bulk finalisation

The default overview covers the existing moderated students, separately from the
independent moderators' group. It shows ready, attention-required and already
finalised counts, plus the ready group's proposed Pass, Pass with supervisor
follow-up and Fail outcomes. Filter the list by readiness, outcome and source
batch. Open exceptions individually; settled audit/tool disagreements and automatic
Manual check routing do not reopen definite human decisions.

1. Open **Preview cohort feedback & bulk finalise**. Review the consolidated
   feedback or download the **feedback review workbook — not finalised**. Both
   contain the ready students' numbers, names, proposed outcomes and full public
   feedback, without private source material. Spot-check or edit through the
   existing student editor; opening every record is not required.
2. Check the number to finalise, outcome breakdown, attention exclusions and
   already finalised count. Enter the finalising moderator and explicitly confirm
   that the proposed feedback has been reviewed. Staff-edited drafts are clearly
   marked and require an additional confirmation approving their current wording.
3. Choose **Bulk finalise ready feedback**. The server reads current saved sources
   and rechecks each previewed record before saving. Missing decisions, conflicting
   sources, unsuitable wording and stale records are excluded. Records changed
   since preview are excluded with reasons; newly eligible students are not silently
   added. Reopen the preview after edits. Preview approvals expire after two hours.
4. Use **Export finalised students only** for the release workbook, then copy the
   feedback into eLP manually. The review workbook is clearly labelled as a review
   copy and does not authorise release.

List filters do not silently narrow the bulk action: the preview explicitly shows
all eligible students in the selected group. The independent moderators' students
are excluded from the default action. After their feedback is entered and reviewed,
the same workflow is available from **Open independent feedback**.

Bulk finalisation preserves public wording, waivers, provenance and prior history.
Each final record records the moderator, timestamp and bulk operation reference.
Existing finalised records are never replaced by bulk actions, including stale
finals requiring individual attention. Repeating an operation does not duplicate
finalisation history. Only the separate release register is written; moderation,
audits, checking rules, approvals and source feedback histories remain unchanged.
Opening the overview, preview or review download does not finalise any feedback.

### Individual review and release export

1. Search/filter the register and open **Review feedback**. The generated public
   text appears first; historical findings and source documents remain optional
   supporting references. Open **Edit wording or recorded outcome** only if needed.
2. Enter the responsible finalising moderator and confirm the feedback for release.
   A previously recorded auditor or the last finaliser can prepopulate this field.
   Settled records do not ask for a new decision note or a second moderation
   checklist. A genuine gap needs the located final judgement/source reference.
3. Use **Export finalised students only** for actual release. The full-cohort
   alternative includes all 106 students but leaves outcomes and feedback blank
   for unfinished or source-changed records. Pass with supervisor follow-up exports
   as Pass for eLP. Copy the final text into eLP manually.

For the other 41 students, enter the independent moderator's explicit outcome,
student corrections, required supervisor completion and supervisor
follow-up that is not required for resubmission in the existing roster row. Preserve their original feedback in its
private field. No outcome is inferred from free text, no automated checking is
required, and bulk import is not needed for this first release.

The release workbook has one sheet and five public columns: student number, name,
Pass/Fail, final feedback and finalisation status. Internal evidence and notes are
excluded. The existing detailed moderation export is unchanged and remains staff-only.

The private register is `reviews/feedback-release/register.json`, excluded from Git.
It preserves provenance and histories of preparation, staff edits and finalisation.
Source changes are checked before export; affected finalised records are held until
explicitly refinalised. Replacement of finalised feedback requires confirmation.
No feedback is finalised merely because its source moderation has been recovered.

Source validity compares decision-relevant information, not a checksum of every
technical checker field. Reordering criteria, changing groups, extraction-version
metadata and revised explanations that leave decisions and feedback unchanged do
not reopen completed moderation. Changed files, attempts, staff decisions, unresolved
findings or required public instructions remain material. An automatic referral
does not displace a definite recorded human judgement. The editor identifies material
changes specifically. Live editor and bulk-preview tokens remain strict: changes
after opening a preview still require a fresh preview before approval.

V2 evaluation completed **18 November 2026**: **19 criteria approved, one partly
approved and four unapproved**. See [EVALUATION_FINDINGS_V2.md](EVALUATION_FINDINGS_V2.md)
for decisions, evidence limits and next steps, and [TODO.md](TODO.md) for prioritised
fixes. Manual referrals can remain in approved checks. Approvals are specific to
the evaluated criterion/source/version; recommended improvements are separate.
The **All v2** operational snapshot (18 November 2026) requires **304 confirmations**
across 106 submissions, compared with 464 for approved v1 (34.5% fewer). See the
[full-cohort results](EVALUATION_FINDINGS_V2.md#full-cohort-operational-results--18-november-2026)
for provenance and limitations. Fail outcomes remain provisional; staff-time savings
and improved error rates have not been established.

The baseline and implementation notes below describe development before this v2
evaluation; use the evaluation summary for current approval decisions.


Evaluation reference: **Validation baseline v1 — 17 November 2026**, Git tag
`validation-baseline-v1`. See [VALIDATION_BASELINE.md](VALIDATION_BASELINE.md)
and [CHANGELOG.md](CHANGELOG.md) for scope, versions and verification.

Staff-confirmed workspace naming and evaluation clarifications are recorded in
[LAB_SPACES.md](LAB_SPACES.md). This working glossary does not change current v2
checking behaviour; unresolved room aliases and functions still need confirmation.

Development on `validation-v2` follows [TODO.md](TODO.md). The v2
changes accept inserted middle names when the first name and full submitted
surname match, preserve ambiguous name variants for review, stop blank titles
from borrowing risk-table headings, and recognise scoped `Name:` sign-off labels.
Persons-at-risk entries must identify people or groups; counts alone are incomplete.
Readable ratings may place a band before the score, in square brackets or on a
following line. Ranges and calculations without an entered result remain for
review. Explicitly wholly unused/N/A rows do not require ratings or block other
score comparisons; unused-row cleanup is a separate moderator judgement.
Audit statistics show definite-outcome coverage independently of agreement.
These changes are development fixes, not new validation evidence. Existing
approvals are not transferred to the changed checking version, and saved audit
snapshots and baseline findings are not rewritten to apply these fixes.

Version 2 also keeps separate RA sections with their own locations and risk rows,
accepts a dedicated Location field, and uses the agreed computer-activity interpretation.
Course/module codes do not establish a room by their shape. Clear continuation
hazards may share their parent activity within a table, with the association shown
in evidence. Word highlights and explicit bold contrast, PDF bold contrast, and
isolated vector risk-selection boxes are supported; unclear placement/marks stay
manual. Floating Word text is associated only where its field placement can be
established; otherwise missing-field claims need review.

Specialist answers misplaced in reference fields or qualified with extra wording
receive a specific moderator-judgement explanation. Unchanged blank primary
answers remain issues. Accepting a misplaced Yes answer retains Supervisor check
and its supporting-assessment feedback. Unrecognised questionnaire coverage is
manual, rather than inferred from hazard headings. Missing ethics forms receive
one form-level finding with dependent checks skipped, while uncertain extraction
or alternative templates require inspection.

After comparing audits, expand a check and use **Record agreed interpretation**
to classify a human error caught by the tool, a tool error, an interpretation
disagreement, an audit recording/category gap, or an unresolved case. Enter a
reason. These records remain separate from the audit and automated snapshot;
statistics show their counts against all audited cases without rewriting initial
agreement. The audit's **Other corrections not covered by the checks** box records
feedback that did not fit the rubric. These research records do not change
moderation outcomes, automation approvals or student feedback.
Earlier private `evaluation-decisions.json` records also appear read-only, with
their original classifications, reasons and separate per-check counts. They are
not converted into new adjudications or treated as validation of changed checks.

The student self-checker remains a proposal. Its recorded requirement is to ask
students to remove project-only consequences (such as milestone delays) while
retaining their own relevant health-and-safety descriptions, and to correct
technical rating/answer-placement defects. This moderator update does not implement
a student-facing application. Synthetic tests and mocked AI verify implementation;
fresh independent evaluation is still needed before approving the changed checks.

A local Django app for reviewing completion of KB6060 risk assessment and ethics
forms downloaded as a ZIP from Turnitin/Blackboard.

Upload a submission ZIP to run 24 completion checks plus a word-limit reminder, inspect a sortable/filterable
matrix, review evidence, record moderation decisions and export CSV or Excel.
The app uses local files and does not need a database.

Checks are grouped in review order: RA information, risk assessment, risk
assessment sign-off, ethics, and ethics sign-off. Individual findings, matrix
columns and exports share that order. Saved reviews use the current grouping
without changing their findings, evidence or moderator decisions.
**Specific area or activity** belongs to **RA information**,
alongside document readability, assessor identity and project details. Activities–
facilities consistency remains in Risk assessment.
The **Appropriate field entries** check sits alongside the student and supervisor
risk sign-offs, in both independent audits and moderation, so job-title suitability
is considered with sign-off completion. It also covers other populated answers
that are misplaced or contradictory; dedicated missing-field checks remain separate.

## Run locally on Windows

Python 3.13 is used for development. From this folder in PowerShell:

```powershell
.\.venv\Scripts\python.exe manage.py runserver
```

Open http://127.0.0.1:8000/ in your browser and choose your ZIP.
No database creation or migrations are required.

## Recreate the environment

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe manage.py check
```

`requirements.in` lists direct runtime dependencies. `requirements.txt` pins the
installed runtime packages. The corresponding development files add pytest,
pytest-django and Ruff.

Runtime libraries cover Django, the OpenAI SDK, Word documents (`python-docx`),
PDF processing (`PyMuPDF`), Excel exports (`openpyxl`) and local environment
configuration (`python-dotenv`). ZIP and CSV support come from Python itself.

## Configuration

Settings load an optional `.env` file. Copy `.env.example` to `.env` and fill in
values as needed. An OpenAI API key is not needed for rule checks. To enable AI,
set `OPENAI_API_KEY` and optionally `OPENAI_MODEL` (default: `gpt-5-mini`), restart
the server. "Include AI language checks" is selected by default when AI is
configured; untick it to run rule checks only. You can also
run AI on an existing review or retry failed AI checks.

AI checks send extracted text to OpenAI, use structured responses, request
`store=False`, and check that quoted evidence exists in the submission. Original
documents are not uploaded to OpenAI. API charges apply. A missing key, failed
request, refusal or unverifiable evidence never counts as an AI pass. Tests mock
the API; live model accuracy must be evaluated using moderated examples.
Completed AI checks with rejected evidence or out-of-scope conclusions are shown
as needing moderator review, separately from checks awaiting assessment. Retry
remains available; repeated verification failure is not described as still
running, and no rejected conclusion counts as a pass.

Quote verification includes extracted table cells and rows as well as paragraph
text, so PDF reading order does not invalidate genuine table quotes. H&S evidence
must relate to an extracted hazard. Failed H&S evidence checks retain the rejected
assessment, state that no AI conclusion was accepted and are marked for retry;
they are not student errors and are not described as processing still running.

Without AI, language-based criteria remain manual checks. Fixed rule failures
cannot be waived by AI. A reviewer can override any result and optionally add an explanatory
note, while the automated finding is retained. No API key is exposed to the browser.
If an AI field-entry assessment discusses signatures or risk-rating calculations,
it is excluded and retained for audit, and that check is marked for reassessment
using the pending AI button. This indicates a missing usable AI assessment, not
an identified student error; it does not clear any independent rule findings.

Debug mode is enabled for local development. The app generates a temporary
development secret if no key is configured. Set a stable private
`DJANGO_SECRET_KEY` and disable debug mode before hosting.

There is no database, Django admin, authentication or database-backed session
middleware. Student documents, review data, `.env` and `.venv` are ignored by Git.
Do not put student details in source code or commit messages.

Risk-table completion checks only activity/equipment/materials, hazard, persons at
risk and control measures. Missing fields are named by row with targeted completion
instructions. Severity, likelihood, initial Risk Rating and post-control Final
Result belong exclusively to Risk ratings completed, which names every missing
numeric field. Final Result may be a score alone; a multiplication expression is
optional. The reduction check is skipped while missing numeric values prevent a
comparison; an identifiable equal/higher score elsewhere remains an issue. These
rule findings refresh in saved reviews without AI calls, retaining moderation
notes, decisions and previous automated findings.

## Generating eLP feedback

Each submission has **Generate eLP feedback**, enabled only after processing and
applicable AI work finish, all findings requiring confirmation have been reviewed and unresolved
moderator judgements have a final outcome. Excluded earlier attempts and incomplete
checklists cannot generate feedback. The same restriction is enforced on the
server; there is no feedback draft before moderation is complete.

Generation is local and deterministic: no extra AI call and no automatic sending
to eLP. It produces one plain-text block with the final result, a consolidated
numbered list of student corrections and separate supervisor follow-up. Confirmed
issues remain Fail; accepted specialist follow-up remains Pass with follow-up.
Overridden Complete findings, skipped dependencies, internal moderation notes,
source quotes and rejected AI/extraction claims are not copied into feedback.
Duplicate rating-completion/reduction findings are consolidated. Repeated missing
scores are grouped by rows, administrative questions are named, and tutor feedback
identifies the actual checklist items. Required supervisor signatures are grouped
by form, separately from follow-up that is not required for resubmission; Yes/No instructions appear once.
The feedback uses action wording rather than raw check messages. Format upgrades
require regeneration, preserve previous versions and carry forward manually edited
public wording where the reviewed findings have not changed. Required missing
supervisor fields remain correction-required even though addressed to the supervisor.

Confirmed Area/Activity and Low Risk selection issues use their known rubric
requirements for correction wording, including when the moderator escalates a
Manual check to Issue found. Private notes remain excluded.

Where a moderator override identifies an issue but has no safe, specific public
wording, the generator asks for student/supervisor feedback text rather than guessing
or copying internal notes. **Edit feedback wording** lets the moderator refine the
text before copying; confirmed items cannot simply be omitted from this form.
Use **Copy eLP feedback** to paste the result into eLP. Copy verifies that the review
and generated wording are still current. Changed findings block generation/copy
until moderation is complete again; stale saved feedback is not shown. Generated
text, format version, source signature, wording and generation history remain in
the private review JSON. Refreshing a review does not generate or send feedback.

### Bulk eLP feedback

Open **Bulk eLP feedback** from the review grid, then choose **Generate feedback for
all ready students**. This uses all currently selected attempts, regardless of
grid filters. Only students with complete moderation and specific feedback wording
are included. Unreviewed findings requiring confirmation, unresolved judgements, pending AI work and missing public
wording exclude only the affected selected students. Earlier attempts are shown
in a separate retained-attempts section and are not counted as excluded students.
Exclusions are listed with reasons and
links to finish the work; no draft feedback is generated for them.

Each included student has a labelled block and an individual Copy button. **Download
Excel with feedback** produces the same workbook as the main **Export Excel** button,
with **eLP feedback** as the final column on the Snapshot sheet. It contains the full
selected cohort; feedback cells are populated only with current generated text,
and remain blank for unfinished, ungenerated or stale cases. Line breaks are retained
and feedback cells wrap in a wider column. The Findings and decisions sheet remains
separate, including internal notes; copy only the eLP feedback cell to the student.
Copy buttons include only that student's feedback text. Existing current feedback, including individually edited
wording, is preserved; repeated bulk generation does not duplicate generation
history. Changed findings or attempt selection invalidate old downloads. The page
can be revisited without generating anything, and generation sends no AI requests
or feedback to eLP. Keep downloaded feedback private like the source submissions.

## Overall outcomes and eLP

The grid's Overall column, overall summary counts and CSV/Excel summary outcomes
use **Pass**, **Pass — supervisor follow-up**, and **Fail — correction required**.
The first two correspond to Pass in eLP; the third corresponds to Fail. Unresolved
Manual check, Needs moderator review and Unable to check findings give an overall
**Needs moderator review** outcome. A correction-required issue takes precedence
over supervisor follow-up. Check-level labels remain Complete, Supervisor check,
Issue found and their existing review/readability labels. Summary counts count
whole submissions by overall outcome; check filters still match individual checks.
The moderator records the final result in eLP; the app does not update eLP or
certify safety adequacy. These wording changes preserve saved findings and decisions.

## Validation and routine moderation

Open a saved batch, or **Choose workflow** from the grid, for two choices:
**Validate the tool** opens independent audits; **Moderate submissions** opens the
moderation grid in Routine mode. **Global approvals**, linked in the main navigation,
provides one workspace-wide list of approved criterion/source pairs, evidence,
recommended fixes and withdrawal history. New reviews start in **Moderate submissions**
when current shared approvals exist; otherwise they start in **Validation**. Existing
reviews retain their chosen workflow. Validation mode keeps explicit confirmation
requirements and independent audits even when a shared approval exists.
No check is automatically declared validated by this change.

From **Saved reviews**, use **Validate the tool — open without tool findings**
to choose a submission without viewing its results. Open the originals, record
an outcome for every criterion and optional submission notes,
then **Save audit & return to overview**. Saving does not reveal tool results.
The overview shows how many selected submissions have been audited. Only once
every selected submission has a complete saved audit and processing is finished
does **Compare with tool** become available. Its server-side gate also blocks
direct or old per-submission comparison links before completion. The batch report
uses each submission’s latest saved audit and its captured automated snapshot;
repeat saves do not increase the audited-submission count. Differences are shown
first in compact rows with the audit and tool outcomes side by side. Select a row
to expand its explanation; matching checks are collapsed separately. The report
uses normal page scrolling rather than a nested scrolling table. Adding an unaudited
attempt to the selection blocks comparison again. On the audit overview, record one auditor
name for the batch, with optional total time taken and overall comments. You can
start and save submission audits before entering any of those details, then add
them when finished. Comparisons use the batch auditor when an earlier audit
snapshot has no recorded name. Each saved submission audit retains its auditor
and overview details as a snapshot; editing overview details does not relabel
earlier records. There is no per-file time or name field.
Use **Mark remaining checks Complete** after inspecting the original, then select
any exceptions using the inline choices. The shortcut fills only unanswered
checks, preserving existing exceptions; no outcomes are preselected on entry. Each save retains a separate independent
audit and snapshot of original automated findings and AI metadata, without changing
moderation decisions. The comparison identifies differences, not adjudicated false
positives or missed defects. A second reviewer can record another audit without
seeing the first on the entry page. Prior exposure cannot be undone by hiding results.
Select unfamiliar cases and include passed checks as well as flagged ones; these
records do not themselves establish reliability or authorise research reuse.

After staff validation, record the evidence reference and explicitly approve the
relevant criterion/source pairs in **Global approvals**, then choose **Moderate
submissions**. Approvals apply to all matching existing and future moderation reviews
in this local workspace; Rule and AI findings are approved separately. You can edit
the evidence/notes or withdraw a decision globally. Older Study settings links redirect
to this page. Once the shared registry is initialised, batch-only approvals cannot
reactivate a withdrawn global decision.
Only approved, version-matched clear **Issue found** and **Supervisor check**
findings bypass individual confirmation. They feed correction wording or supervisor
follow-up through the existing feedback generator. They are labelled automatic,
not human-reviewed. Complete results continue to need no routine confirmation.
Uncertain, unreadable, unapproved or overridden findings still require moderation;
reviewed but unresolved judgements continue to block feedback. Public wording,
processing, attempt selection and outstanding AI requirements still apply.

Approvals are bound to a fingerprint of checking/extraction/prompt code and the
configured model. Findings record that fingerprint when generated. A changed
version/model or a legacy finding without matching provenance cannot use an
approval. Model aliases may change externally; this fingerprint is not a guarantee
of a provider's immutable model revision. Record model and guidance details in the
validation evidence reference. Restart after software changes. Settings changes
retain originals, decisions, audit snapshots and settings history, and never rerun
checks or start AI. Review existing findings manually rather than rerunning a
batch solely to remove a legacy provenance warning. Feedback readiness and the
review queue use the same approval policy; revoking approval restores the gate.

## Moderator workflow and progress

Supporting evidence opens automatically only for the currently selected rule.
Review links bring that rule into view after its evidence opens.
Selecting another rule collapses the other evidence panels; the active panel
can still be collapsed manually.


The Student and Overall headings are clickable sorting controls; click again to
reverse the order. Overall sorts Fail first, then moderator review, supervisor
follow-up and Pass. Filters are preserved. Overall outcome is also in Sort by.

In Validation mode, use **Review next** beside the progress count to open the first unreviewed flagged
check in the current grid order and filters, or click any grid result. If filters
hide all remaining checks, **Review next (all checks)** explicitly opens the wider
queue. The link disappears once all flagged checks are reviewed. Both routes
preserve the return context and open the finding and moderation dropdown. **Save decision
& return to grid** keeps the current filters, sorting and browser-tab scroll
position (including horizontal table scrolling), and briefly highlights the saved
cell when it is still visible. **Save and open next** moves through outstanding
unreviewed flagged checks in the current grid order and filters, returning to the grid when
no other matching check remains. The back link also keeps your grid filters.

Each row shows Reviewed below its overall outcome when all its flagged checks
have saved moderation decisions; otherwise it offers a Review link to the first unreviewed flagged finding, or
shows partial progress. The review link is spaced below the outcome pill. This uses all flagged checks for the student, regardless of grid filters.
Rows with no flags say No flagged checks rather than implying human review.

Progress is separate from outcomes. Saving **Keep automated result** confirms that
you checked it. A confirmed Issue found stays red, with a Reviewed mark, because
student correction is still needed. Saving Manual check or Unable to check counts as reviewed, leaves that check
unresolved for follow-up and removes it from the default next-check queue. Resolve it to Complete, Issue found or Supervisor check when the evidence permits. Review notes are optional, including when changing a result.

The **Needs moderator review** filter selects rows with unreviewed flagged cells;
other cells are muted for context. **Reviewed but unresolved** shows saved Manual
check and Unable to check results separately. A counter shows reviewed and unreviewed flagged
checks across the selected attempts, independent of matrix filters. Complete
results can still be opened and reviewed. Saved decisions and progress persist
across restarts; materially changed automated findings require another review,
while retaining previous decisions and history. Older saved decisions count as
reviewed when their outcomes are resolved. Scroll restoration requires browser
session storage; navigation and saved decisions work without it.

Specialist Assessments distinguish **Supervisor check** (Yes selected: supporting
assessment follow-up), **Issue found** (blank or unchanged Y/N answers), and
**Needs moderator review** (uninterpretable or ambiguous answers). All clear No
answers are Complete. Missing answers remain issues even if another answer is Yes.
Saving Supervisor check accepts it as moderated feedback; it stays visible for
supervisor follow-up and is skipped by Save and open next. This status is available
in the outcome dropdown, grid filters and exports. Other Manual check findings
keep their existing meaning. Saved specialist findings refresh without AI calls,
retaining decisions, notes and prior findings; existing moderation is retained
when only the follow-up label changes on unchanged evidence.

Activities–facilities consistency is **Skipped** when Area/Activity is blank.
The omission belongs to Specific area or activity. The skipped consistency check
is excluded from the AI response schema, pending/retry counts and moderation queue;
it is neither a pass nor a duplicate error. Saved reviews refresh this dependency
without AI calls, keeping prior findings and decisions for audit. Once a workspace
is present, consistency remains a separate comparison with the actual activities.

## Selecting submission attempts

New uploads default to **Analyse only the latest submission per student**. The
selection uses Blackboard's `Date Submitted` metadata, falling back to its
timestamped attempt filename, never filesystem modification dates. All attachments
from a selected attempt stay together. Separate assessments stay separate when
identified by their metadata filenames. Earlier attempts and originals remain
saved and accessible, including findings, moderator decisions and history.

Missing/unreadable timestamps retain all that student's attempts; ties retain all
latest attempts. The review displays a warning rather than choosing arbitrarily.
Attempts without a reliable student number are retained. Counts, processing, AI
retries and exports use the selection; matrix filters do not narrow exports.

Saved reviews have the same selection control. Existing reviews keep all attempts
until changed. Applying a selection starts no analysis or AI calls. If restoring
all attempts exposes unprocessed submissions, choose **Resume analysis** to process
them. Selection cannot change while processing is running.

The three required student declarations include template wording about the data
retention schedule and guidance. Their actual checkbox selections are checked;
the supervisor declaration is separate. Saved declaration findings refresh without
AI calls, retaining previous findings and moderator decisions.

## Saved reviews and processing

Each review is stored under `reviews/<random-id>/`, including original documents,
extracted text, findings and decisions in `review.json`. Files persist across app
restarts. This folder contains student data; keep it private and manage retention
according to your normal university process. UUID URLs identify local reviews;
there is no user authentication. This version is intended for localhost only.

The browser polls progress while one background worker processes submissions in
sequence. Keep the server running. Results are saved after each submission; if
the server stops, reopen the review and choose Resume. This is a single-process
local worker, not a production task queue or multi-user service.

Word fields, checkbox controls, tables and embedded images are read directly.
Legacy `.doc` submissions are imported too. On Windows, installed Microsoft Word
converts a private local copy to DOCX with macros and link updates disabled; the
original stays unchanged and remains the download. Converted copies are cached
under private `reviews/.converted-docx/`, including for image evidence. Conversion
failure leaves the student's row visible as Unable to check instead of dropping
the file; save a DOCX/PDF copy to retry if Word is unavailable.
Supported freehand Word drawings in a signature paragraph, or its immediately
preceding blank paragraph in the same cell, also establish presence and have a
rendered preview. Page-positioned or unsupported nearby drawings remain manual;
simple lines do not establish signature presence. Existing reviews refresh this
extraction without AI calls, preserving moderator decisions and prior findings.
PDFs with readable text support ruled nine-column RA tables (including aligned
continuation pages), wrapped text, readable checkbox glyphs, tutor checklist marks
and typed sign-offs. Sign-off dates remain separate across student/supervisor
columns and may omit the colon after Date when followed by a clear date value.
Embedded PDF images clearly positioned in a signature field
are attached as presence evidence and displayed with the finding; handwriting is
not transcribed and authenticity is not assessed. Header logos, distant images,
full-page scans and ambiguous image placement do not establish signature presence.
An image can start above the signature label when it stays in that signatory's
ruled table cell, or follows their name/role in the same sign-off area. It must
overlap the signature line and stay within the field boundaries.
Images overlapping the name/role or belonging to another sign-off remain manual.
Unsupported tables, unclear selections and ambiguous signature graphics remain manual.
An unmistakably blank, readable PDF signature area is Issue found. The reader
checks the rendered field and nearby images, vector marks, annotations and widgets;
possible unrecognised ink or ambiguous graphics keep the result manual.
Risk tables can use grouped row identifiers (e.g. A1, A2, B1), repeated headers
and merged section headings. Control text continued on another page is attached
to its original row. Headings and the specialist-assessment section are excluded
from risk-row counts; ambiguous, duplicated or missing row sequences remain manual.
Saved PDF reviews refresh rule findings without AI calls, retaining originals,
previous findings and moderator decisions; the activities–facilities AI comparison
is marked for rechecking against the recovered rows.
Scanned PDFs without readable text are marked unable; OCR is not implemented.
Supported documents are `.docx` and `.pdf`. Unsupported files are listed on the
review. Limits are 150 MB per ZIP, 25 MB per document, 500 MB expanded archive
size, 500 submissions and 60 pages per PDF. ZIP paths are never extracted.

Excel contains the snapshot and a second sheet with findings, evidence and notes.
CSV contains the snapshot. Exports include every submission, regardless of the
current browser filters. Formula-like input is exported as text.

## Agreed review scope

- Check both risk assessment and ethics forms for correct completion.
- Require Low Risk ethics, with Medium unselected.
- Compare the assessor with the submitting student's identity from ZIP metadata.
- Require Area/Activity or a dedicated Location field to identify a clear manufacturing process, test procedure,
  or named room/laboratory. Rules flag blank fields; AI assesses every nonblank
  entry by meaning, allowing equivalent terms and abbreviations without an approved
  list. For a computer-work RA section, a clear computer-based activity description
  is sufficient; a named workstation or room is not required. Meaningful workspaces
  such as computer labs, a library workspace, home office or PC at home also qualify.
  Bare "home" or generic "Design/Simulation" needs correction. The Area/Activity
  entry or its dedicated Location field must supply a meaningful activity,
  workspace/setup or a specific process/procedure;
  AI must not borrow missing CAD/CFD or other specifics from elsewhere to pass it.
  AI must use actual RA and ethics activity evidence to establish
  computer-only work in that section. Separately assessed physical work, including conditional work,
  belongs with its own RA section,
  rather than infer it from the title. Missing or ambiguous activity evidence
  remains manual. Blank locations remain issues. Generic locations for physical
  work still require a clearer process, procedure or workspace. Without AI,
  the content assessment remains manual. Version 2 does not silently refresh frozen
  evaluation findings or run AI on saved batches.
  No approved lab list is required.
  "Engineering laboratories" is too generic for physical work, even when a
  university/city and computer facilities are also named. The Area/Activity or Location entry
  must name a lab/room or identify a specific process/procedure itself. For
  confirmed computer-only work, stated university computer facilities suffice;
  unused generic laboratory wording does not create a requirement for a named lab.
  Conditional physical work is included; unclear activities remain manual.
- Compare the workspace with RA activities/equipment and ethics research activities.
  The separate activities–facilities check reports clear, evidence-backed conflicts
  between workspaces and activities as Issue found. Missing/vague location specificity
  belongs to the location check; borderline/ambiguous comparisons
  and unverified evidence remain Manual check. Extraction failures alone do not
  establish a student error. A clear computer-activity section does not require a
  named workstation. The check
  distinguishes simulation-only projects from physical work, and requires evidence
  from both the location and activity descriptions before accepting an AI finding.
  It does not certify room suitability. Without AI it remains a manual check.
  Existing reviews gain this pending check without changing previous decisions or
  making API calls. Run pending AI checks to evaluate it on those submissions.
- Accept typed and image signatures; check presence only, never authenticity.
  Word images in an otherwise empty paragraph immediately before the signature
  label count when they follow the name/role in the same sign-off block. Images
  before the signatory details or separated from the label by other text are not
  inferred to be signatures. These images are included in supporting evidence.
  Ethics sign-off dates may appear on the next paragraph beneath Date:. The
  reader includes that value, but does not cross another field label to fill a
  blank date. Saved sign-off findings refresh while preserving prior findings,
  moderator decisions and notes.
- Show available embedded images alongside supporting evidence and display each
  repeated source extract once. Images alone do not establish authenticity.
- Treat blank administrative answers or unchanged Y/N options as unanswered
  questions (Issue found), rather than ambiguity. An uninterpretable answer stays
  a manual check. Retained Y/N options with an answer entered in a reference field
  remain a completion concern; improve the student instructions rather than
  silently treating incorrect placement as correct completion.
  A clearly highlighted single Y or N also counts as an answer. The reader
  supports direct Word text highlights, PDF highlight annotations and coloured
  PDF background rectangles. Both options or partial/unclear highlighting require
  manual review. Highlighted Yes specialist answers still require supporting
  assessment review. Highlighting in a reference field does not answer the Y/N
  question. Evidence and Excel findings identify the interpreted highlighted choice.
  Explicit bold contrast is also recognised in Word/PDF; inherited styling alone
  is not a selection. Interpretable reference-field answers require moderator
  judgement about placement, retaining supporting-assessment follow-up for Yes.
- Flag missing fields, unchanged example rows and inappropriate entries.
  Standalone template word-limit labels, including split fragments such as
  `words maximum).`, are excluded from response extraction and AI text.
  They are not evidence of a student entry error; original extracted text is retained.
- Job Title must identify the person's role: Student (or an equivalent student
  role) for the student and a staff role for the supervisor. A project title in
  this field is an issue requiring correction. Exact project-title matches are
  checked by rules; AI assesses other entries by meaning, with borderline cases
  left for manual review.
- Appropriate field entries assesses the meaning and placement of populated
  answers. Required-field omissions belong to dedicated completion checks (e.g.
  a missing ethics supervisor name is reported only under Ethics details).
  Whether the assessor matches the submitting student belongs only to Assessor
  is student, even when AI describes a staff name as a wrong-field entry.
  Duplicated AI omission findings are withdrawn and marked for reassessment;
  the dedicated result, moderator decisions and original findings are retained.
- Require final risk scores to be strictly lower than the entered initial scores;
  equal/higher scores are flagged with the row and both values. This completion
  rule does not certify that the initial scores or controls are appropriate.
  Multiple ratings in a row are read as separate nonblank lines and compared in
  listed order. Severity, likelihood, initial and final entry counts must match;
  a mismatch is an issue requiring clarification/correction. A missing opening
  or closing bracket around a risk band (e.g. `4L)`) does not obscure the
  numeric score; the original wording stays in the evidence. Uninterpretable
  entries remain manual rather than being paired by guesswork. Evidence shows
  the rating columns, including all final entries, separately from control text.
  This does not verify that each hazard and control corresponds to its rating.
  Saved reviews refresh these rule checks without AI calls, preserving original
  findings, moderator decisions and notes.
  Decimal Word list numbering is included when reading visible rating values.
  Risk bands may use L/M/H or the full words Low/Medium/High, with or without
  parentheses; the entered numeric score is read without judging the band.
  A final score alone (e.g. `9` or `9 (L)`) is sufficient; showing its multiplication
  is optional. Initial severity/likelihood and post-control multipliers may differ.
  AI field-entry checks do not assess risk-score calculations or compare those multipliers; rating
  completion and score reduction belong to the dedicated rule checks. Older AI
  field-entry findings about ratings are withdrawn and marked for rechecking,
  preserving moderator decisions and the original finding for audit.
- Clear non-H&S hazards confirmed by evidence-backed AI are Issue found and
  require student correction. Potential rule flags without AI confirmation and
  borderline or ambiguous judgements remain Manual check.
  Borderline mixtures of health effects and minor project-only wording use Needs
  moderator review; a confirmed protected non-H&S rule finding remains Issue found.
  Older rule flags with appended AI observations are marked for rechecking;
  use Run pending / retry failed AI checks to apply the updated status logic.
  The review page shows the number of pending AI checks when any are waiting,
  across the full review regardless of the current filters. Failed or disabled
  AI checks are not counted as pending unless explicitly marked for rechecking.
- Require manual supporting-document checks for specialist Yes answers, including
  conditional or ambiguous answers.
- Keep assessment of substantive adequacy with the supervisor.
- Provide a sortable/filterable table, evidence, manual decisions and CSV/Excel
  export. Reviews persist as files rather than in a database.
- No student roster or missing-submission tracking is required.

## Student version and guided completion (proposed)

The implemented app is the local moderator checker. A student-facing version is
planned for use before submission and supervisor approval; it is not implemented
or ready for public release. It must exclude supervisor sign-off checks while
retaining student-owned required fields and signatures and applicable RA/ethics
completion checks. It must not expose moderator decisions or internal notes.

An interactive completion app is an option to investigate, not an agreed
replacement for the checker. Students should attempt their own answers before
receiving explanations and targeted questions, then revise and explain selected
decisions. Assess meaning, including synonyms and abbreviations; do not maintain
an approved-answer list. Avoid generating hazards, controls or replacement answers
for students to accept without understanding. Any export must fit the required
institutional document format.

Both student approaches support preparation; neither approves work, certifies
safety or replaces supervisor review of substantive adequacy. Fewer omissions or
cleared warnings alone do not demonstrate learning.

## Development examples and SoTL evaluation

Continue developing the checker against the four current examples. Preserve the
original first submissions, obtain staff-agreed expected findings, record changes
to criteria and extraction, and check that a fix does not break the other cases.
These examples are development cases: repeated tuning against them is not
independent validation. Keep a separate set of unfamiliar submissions out of
development for later validation, with authorised access and research reuse.

The current cohort is the planned baseline for a Scholarship of Teaching and
Learning (SoTL) project. First submissions are reported to have supervisor sign-off;
confirm its recorded presence in the original submitted versions. Staff validation
and baseline analysis are planned, not completed. The main baseline outcome is the
number and percentage of first submissions requiring correction under an agreed
rubric, with types of confirmed deficiencies and subsequent correction cycles.
Do not equate an AI warning or unresolved manual check with a failed submission.

Staff must inspect original documents and validate both candidate flags and cases
the tool passed. Include independent second review of a defined subset, document
disagreements, and separate confirmed deficiencies, false positives, missed errors
and unresolved cases. Freeze and record rubric, software, prompt, model and guidance
versions for each evaluation phase; preserve original and revised documents
separately. Mocked API tests do not establish live model accuracy.

Distinguish completion defects and internal inconsistencies from substantive H&S
concerns. A deficient signed document does not by itself establish unsafe practice,
legal liability or the depth of a supervisor's review. The checker does not assess
control adequacy. Address current safety concerns through normal institutional H&S
routes while the research develops.

A later study could compare guidance alone with the checker, or guided completion
with feedback after drafting. Measure learning through independently assessed,
unfamiliar RA tasks completed without the tool and students' explanations of their
judgements. Interviews can help explain findings but are optional. Establish the
institutional ethics and data-use route before research reuse, recruitment or
additional research collection; routine moderation permission is not automatically
research permission. Do not infer learning or causation from historical document
comparisons alone.

The working brief, open decisions, literature and publication plan are maintained
in the [Notion SoTL project](https://app.notion.com/p/417bfb2f776281d58e9ce35e6a430e7e).

## Development checks

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

With Node.js available, check grid navigation and scroll restoration with:

```powershell
node --test moderation/tests/workflow_navigation.test.cjs
```

**Ethics word limits** is a reminder only: it remains visible, greyed out in the
audit, and is skipped by the checker. It requires no audit answer or moderation
decision and contributes no outcome, correction feedback or validation comparison.
Older word-limit findings and decisions remain stored for history but do not
affect current results. The tool does not count or assess ethics response words.

The completed batch comparison also shows **Statistics by check**. Each criterion
uses the latest audit per selected submission and its captured original tool
outcome, with links to all underlying cases, including matches. Agreement is the
exact three-way outcome agreement among pairs where both outcomes are Complete,
Issue found or Supervisor check; it is shown as numerator/denominator and percent.
Auditor uncertainty, tool uncertainty/unavailability and skipped outcomes are
reported separately and excluded from that denominator. Uncertainty counts may
overlap. Potential missed corrections mean audit Issue found versus tool Complete
or Supervisor check; potential extra corrections are the reverse. Supervisor
follow-up disagreements are separate. These are comparisons to the auditor, not
adjudicated false positives/negatives or independently established accuracy.

Source, recorded checking version and AI model are broken down separately; missing
version metadata is explicit. Do not treat a pooled total across versions/sources
as validation of one current check. Cases without correction-required examples
are highlighted: matching passes alone do not test defect detection. No statistical
threshold, software test result or agreement percentage automatically approves a
check. Development cases remain development cases even when these statistics are
shown. Independent staff adjudication and the agreed evaluation design remain
necessary before recording approval in Global approvals.

In **Statistics by check**, expand a criterion and use **Approve this check** next
to the relevant source/version group. The evidence reference is recorded
automatically; a validation note is optional. The action is a staff decision, not
automatic statistical certification. Only represented, current-version source
results with definite audit comparisons can be approved here; AI groups must also
match the configured model. Older/unversioned groups remain visible but cannot
approve the current version. A changed audit selection, latest audit, overview
details or checking version rejects a stale approval request until the comparison
is reloaded. These actions also publish or withdraw the decision in **Global approvals**
for all matching moderation reviews; they do not change an existing review's workflow mode,
override saved findings, remove uncertainty or start AI.
**Withdraw approval** restores confirmation requirements for unreviewed findings.
Actions and previous approval details remain in the settings history. Repeated
identical approval requests do not duplicate the batch history. Global changes retain
previous evidence and notes in a separate private workspace registry. The global page
rejects stale forms after another approval change. The checking/extraction/prompt/model
fingerprint is unchanged by this workflow-only update; the 21 explicitly approved v2
source decisions have been published without modifying their evaluation records.

Use **Edit audit** on the audit overview to correct a saved outcome. The latest
selections and notes are prefilled. Saving appends a revision and preserves the
original automated snapshot; previous audit versions remain stored and the
submission counts once. Changes made after seeing tool results are amendments,
not new independent validation observations.
