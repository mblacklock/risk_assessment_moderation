# Changelog

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
