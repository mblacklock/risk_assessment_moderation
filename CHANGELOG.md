# Changelog

## Match release readiness to routine moderation — 23 November 2026

- Reuse version-matched validated findings accepted by the main routine-moderation
  workflow, retaining approval provenance and distinguishing them from human review.
- Preserve staff decisions, waivers and independent audits; withdrawn or unknown
  approval/checker versions continue to block release. No approval changes or AI.

## Preserve reviewed feedback through technical refreshes — 23 November 2026

- Compare decision-relevant sources for durable feedback readiness. Technical
  extraction metadata, grouping, ordering and harmless wording refreshes no longer
  reopen unchanged judgements. File, attempt, staff-decision and material feedback
  changes still block release; live preview tokens remain strict.
- Support dated, source-bound conversation decisions in release-only provenance,
  preserving batch acceptance separately from specific criterion judgements and
  retaining later superseding decisions. Keep transcript material out of public
  feedback and never use batch acceptance as a blanket Pass.
- Allow targeted proposal recovery without touching unrelated release records,
  staff drafts, finalised text or original moderation/evaluation histories.
- Show recovered agreements in optional supporting information and describe
  material source changes in the editor. No checking, AI or real finalisation.

## Bulk feedback finalisation — 23 November 2026

- Add separate overviews for existing moderation and independent staff feedback,
  with readiness counts, proposed outcomes, exception reasons and filters by
  readiness, outcome and source batch.
- Add a consolidated public-feedback preview and a clearly labelled review Excel
  workbook, allowing cohort spot-checks without opening every student individually.
- Require explicit moderator approval of the exact previewed records; staff-edited
  drafts require additional confirmation and retain their wording unchanged.
- Recheck readiness and live source validity at execution. Exclude changed,
  unresolved or incomplete records with reasons, never replace existing finals,
  and record the moderator, timestamp and operation reference per finalisation.
- Make repeated operations idempotent and keep the finalised-only release export
  restricted to current, explicitly finalised public feedback. No automatic upload,
  AI rerun or changes to moderation, validation, approvals or checking behaviour.
- Verify with synthetic records; no real student records are finalised during
  implementation or testing.

## Recover completed moderation for release — 23 November 2026

- Reconstruct feedback from saved operational decisions, staff audits, subsequent
  agreed interpretations and linked original manual moderation workbooks, without
  rerunning checking or AI or rewriting any source records.
- Retain agreements across unrelated audit revisions, recognise actual later
  criterion edits and distinguish automated referral routing from human judgement.
- Preserve explicit operational Pass results, recorded waivers, superseded history
  and consistent previously edited public wording. Do not turn technical rubric
  defects into new academic Fail outcomes automatically.
- Separate genuine saved-decision gaps from missing wording; use controlled,
  specific public instructions and keep raw comments, research annotations and
  technical source material private.
- Put generated feedback first in the editor. Settled records need only wording
  review and explicit release finalisation; detailed source history is optional.
- Protect staff drafts/finals during reconstruction and retain the 41-student
  independent manual-entry route and finalised-only public export safeguards.


## Student feedback release register — 23 November 2026

- Add a separate 106-student release register from the selected All v2 roster,
  populated with saved moderation/audit/adjudication proposals for the existing
  65 students and manual-entry places for the other 41 moderators' submissions.
- Require explicit finalisation of the overall outcome and public action sections,
  without repeating 24 criterion decisions. Preserve explicit waivers, original
  edited feedback, superseded interpretations and internal provenance; hold
  ambiguous or conflicting evidence for an explicit staff decision.
- Provide search, sorting, draft/preview, private source references, responsible
  moderator, finalisation date, replacement confirmation and record history.
- Add a release-only Excel export, with all students (unfinished outcomes/text
  blank) or finalised students only. Exclude all private evidence and notes, preserve
  line breaks and force cell text to prevent formula interpretation.
- Detect source changes before export; preserve existing wording during source
  refresh and block changed finalised records pending explicit refinalisation.
- Leave checking rules, prompts, approvals, existing moderation/feedback exports
  and all original validation records unchanged. No checking/AI is run and nothing
  is automatically sent, uploaded or published.


## Shared validation approvals — 18 November 2026

- Add a workspace-wide Global approvals page with separate Rule/AI decisions,
  evidence, improvement notes, version safeguards and approval/withdrawal history.
- Use shared decisions for matching existing and future moderation reviews.
  Inline audit approvals also publish globally; old Study settings links redirect
  to the shared page. Global withdrawal cannot restore an old batch-only approval.
- Start new reviews in moderation when current shared approvals exist. Preserve
  existing workflow choices and independent validation review requirements.
- Publish the 21 explicitly recorded v2 source approvals without rewriting the
  original evaluation records. Manual referrals and overrides still require review.
- Keep checking rules, extraction, prompts, model and evaluated fingerprint
  unchanged. This workflow update is not a new validation of changed checking code.
- Verify with 460 Python tests, 10 navigation tests and Django/Ruff checks; live AI
  was not used for verification.


## After validation baseline v1 — 17 November 2026

### Version 2 development

- Accept inserted middle names while requiring the submitted first name and full
  surname. Shortened/ambiguous names still need review.
- Stop blank project titles from taking risk-table headings as answers. Accept
  `Name:` labels within the correct student/supervisor risk sign-off section.
- Require persons-at-risk entries to identify people/groups, rather than counts alone.
- Read prefix, square-bracket and wrapped risk-band labels. Keep ranges, invalid
  annotations and calculations without results unresolved.
- Exclude wholly unused/N/A rows from ratings and score comparisons, retaining
  row numbers and independently verified nonreducing scores. Present unused-row
  cleanup for moderator judgement rather than requesting numeric ratings.
- Show tool definite-outcome coverage alongside agreement, including source and
  version breakdowns. Coverage includes definite tool outcomes even where the
  auditor was uncertain; agreement still uses comparable definite pairs only.
- Preserve the frozen baseline and saved evaluations. No automatic transfer of
  approvals to the changed checking version and no automatic AI calls.
- Associate locations and risk rows with separate RA sections, including PDF
  page/table positions. Accept dedicated Location fields and clear computer-work
  activities. Keep incomplete/unverified section associations manual. An explicit
  course/module code is not accepted as a room solely on an AI assertion.
- Preserve clear continuation hazards, shared-activity evidence and original
  tables. Improve multi-page PDF table retention without turning extraction gaps
  into student errors.
- Recognise explicit Word/PDF bold contrast as well as existing highlighting;
  account for inherited Word bold styling. Read isolated vector risk checkboxes,
  retaining uncertainty for ambiguous drawings, annotations and image overlap.
- Recognise equivalent administrative question wording without allowing duplicate
  copies of one question to substitute for the other.
- Give intelligible-but-misplaced or qualified specialist answers specific
  moderator explanations, preserve Yes supporting-assessment follow-up when
  placement is accepted, and keep ambiguous questionnaire coverage manual.
- Associate nearby paragraph/character-anchored Word textbox titles with their
  field; uncertain floating text requires inspection rather than a missing-title
  finding. Keep suitability with the field-entry check.
- Route borderline mixed H&S wording to Needs moderator review while protecting
  confirmed non-H&S rule findings. Exclude duplicate example-row findings from
  field-entry quality. Name variations and suspected lab-code conflicts remain
  for identity/location clarification, rather than unverified definite errors.
- Report a missing ethics form once and skip dependent checks; unrecognised
  templates and incomplete extraction require manual inspection.
- Add a separate place for audit corrections outside the rubric, and reasoned
  case adjudications with history and stale-request protection. Report human
  errors caught by the tool, tool errors, interpretation disagreements, mapping
  gaps and unresolved cases separately from unchanged raw agreement statistics.
- Record conditional student self-checker requirements without implementing or
  describing that proposed application as an available feature.
- Display earlier private evaluation-log decisions read-only with their original
  classifications and separate per-check counts. Do not rewrite or reinterpret
  the historical log. Preserve legacy generated-feedback signatures when the new
  follow-up metadata is absent; real follow-up changes still invalidate stale text.

Verification: 454 Python tests and 10 Node workflow tests passed; Ruff checks,
formatting, Django system checks and diff checks passed. AI was mocked in tests;
no paid live AI evaluation was performed. All 47 earlier evaluation-log decisions
were confirmed readable without rewriting the private log.

### Changed

- Saved audits reopen with their outcomes and notes filled in. Corrections append
  a version while preserving the earlier audit and original automated snapshot.
  The submission is still counted once.

- Moved **Mark remaining checks Complete** below the audit checklist. This is a
  layout change; checking rules, audit outcomes and the frozen baseline tag are unchanged.

## Validation baseline v1 — 17 November 2026

This entry summarises the accumulated changes in the current working version.
The fixed evaluation reference is the Git tag `validation-baseline-v1`. See
[VALIDATION_BASELINE.md](VALIDATION_BASELINE.md) for the recorded environment,
model and checking fingerprint. These are development changes, not findings from
an independent validation study.

### Added

- Separate **Validate the tool** and **Moderate submissions** workflows, with
  approval administration kept in **Study settings**.
- Independent audits using original submissions, with tool findings hidden until
  all selected submissions have complete saved audits. Saving returns to the
  overview, which shows audit progress and enables **Compare with tool** when ready.
- One auditor name, optional total time and comments for the batch. Submission
  audits can be started and saved before those details are entered.
- Inline audit outcomes and **Mark remaining checks Complete**, which fills only
  unanswered checks and preserves recorded exceptions.
- Batch comparisons with differences first, outcomes side by side, expandable
  explanations and matching checks collapsed separately.
- Statistics for each check: agreement counts and percentages, possible missed
  and extra corrections, uncertainty, skipped cases and supervisor-follow-up
  differences. Source/version/model breakdowns and links to underlying cases
  support inspection of both matches and disagreements.
- **Approve this check** and **Withdraw approval** alongside the statistics.
  Evidence references are recorded automatically; validation notes are optional.
  Stale approval requests are rejected when their evidence or checking version changes.
- Individual and bulk eLP feedback generation, copying and editing. The standard
  Excel Snapshot ends with an **eLP feedback** column containing current generated
  feedback; unavailable or stale feedback remains blank.
- Selection of the latest submission using submission metadata timestamps, retaining
  every attachment of the selected attempt and preserving earlier attempts.

### Changed

- Routine moderation bypasses individual confirmation for explicitly approved,
  version-matched clear issues and supervisor follow-up. Automatic acceptance is
  distinguished from human review. Unapproved flags and uncertain findings still
  require moderation; unresolved judgements block feedback generation.
- Moderator progress is separate from student outcomes. Every saved decision
  counts as reviewed; **Save and open next** skips reviewed findings instead of
  cycling through confirmed issues. Review notes are optional.
- Added review links and progress labels to the grid, sorting by Student and
  Overall, and restoration of the grid position after saving a decision.
- Supporting evidence opens for the current rule only, with the selected rule
  brought into view.
- Grouped checks consistently across audits, moderation and exports. The first
  group is **RA information**, including **Specific area or activity**.
  **Appropriate field entries** sits beside the risk sign-offs, and **Ethics
  details** is labelled **Ethics information table**.
- **Ethics word limits** is a greyed-out reminder, not an assessed check. There
  are 24 active checks plus this reminder. It contributes no audit requirement,
  moderation task, overall outcome, correction feedback or comparison statistic.
- Overall outcomes distinguish Pass, Pass with supervisor follow-up, Fail requiring
  correction and findings needing moderator judgement. These are completion
  outcomes, not safety approval.
- Enabled AI language checks by default when configured, while retaining the
  option to run rule checks alone.
- Consolidated feedback into specific student corrections, required supervisor
  completion and nonblocking supervisor follow-up. Internal notes and unverified
  extraction/AI claims are excluded from student feedback.

### Corrected and refined

- PDF handling for signatures, embedded images, drawn marks, highlights,
  declarations, dates and risk tables; added legacy Word import through local Word.
- Distinguished verified blank signature fields from uncertain extraction and
  checked signature presence rather than authenticity.
- Accepted final risk scores without a multiplication expression and improved
  handling of rating formats and multiple ratings within a row.
- Kept risk-table content completion separate from rating completion and score
  reduction, with row-specific correction wording.
- Kept area/activity specificity separate from activities–facilities consistency;
  blank Area/Activity skips the latter rather than generating a duplicate finding.
- Refined computer-workspace requirements and distinguished computer-only work
  from physical work, including conditional testing.
- Distinguished unanswered specialist questions, supervisor follow-up and
  genuinely ambiguous answers. Preserved highlighted single Yes/No selections.
- Kept omissions, assessor identity, signatures and rating calculations with their
  dedicated checks instead of duplicating them in AI field-entry judgements.
- Separated outstanding AI work from completed requests whose conclusions could
  not be verified. Failed or unverified processing is not a pass or a student defect.
- Preserved originals, decisions, notes, audit snapshots and histories across
  saved-review refreshes and workflow changes, without silently starting AI.

### Verification

Checks completed on 17 November 2026 before this documentation entry:

- 365 Python tests passed.
- 10 JavaScript workflow tests passed.
- Django system check, Ruff checks, formatting checks and Git diff checks passed.

Routine tests use synthetic fixtures and mocked AI. These results establish
implementation checks, not live-model accuracy, safety adequacy, workload savings
or student learning outcomes.

### Evaluation notes

- Use tag `validation-baseline-v1` for the evaluation. The configured model is
  `gpt-5-mini`; the environment and checking fingerprint are recorded in
  [VALIDATION_BASELINE.md](VALIDATION_BASELINE.md). Retain these records with the
  rubric, prompts, guidance and dependency versions.
- Use unfamiliar submissions for independent validation. Previously tuned samples
  remain development cases. Include passed cases and independently review a
  defined subset; retain disagreements and unresolved findings.
- Record discrepancies before changing the tool. Subsequent changes belong to a
  separate version and must not be presented as validation of this frozen one.
- Agreement statistics describe comparison with the auditor. Uncertain and skipped
  outcomes are excluded from the definite-pair agreement denominator and reported
  separately. Possible missed/extra corrections are not adjudicated error rates.
- No agreement threshold or automated test automatically validates a check.
  Approval is an explicit staff decision, currently scoped to a batch and source,
  with matching checking/model provenance. Older or unversioned results remain
  outside automatic acceptance. Model aliases may change externally.
- The app remains a private localhost moderator tool. Supervisor assessment of
  substantive safety adequacy remains necessary. The student-facing checker and
  guided-completion workflow remain proposals, not implemented features.
