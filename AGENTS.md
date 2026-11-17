# Repository guidance

## Purpose and current state

This is a local Django moderator tool for checking completion and internal
consistency of engineering risk assessment (RA) and ethics submissions. Read
`README.md` for setup, agreed scope, limitations and the SoTL research plan.
Reviews and originals are stored as private local files; there is no database or
authentication. The current app is intended for localhost, not public hosting.

The student-facing version and interactive guided-completion workflow are
proposals, not implemented features. Do not describe them as available or replace
the moderator workflow without a request to implement that change.

## Checking behaviour

- Keep deterministic completion checks separate from AI content judgements.
  Missing evidence, failed AI requests and unverified quotes are not passes.
- Clear defects requiring student correction are issues; manual review is for
  borderline or ambiguous judgements. Evidence-backed AI confirmation of a
  potential non-H&S rule flag must become an issue. AI cannot clear that rule flag;
  without confirmation it remains a manual check.
- Area/Activity must identify a clear manufacturing process, test procedure or
  named room/laboratory. Rules check presence; AI assesses every nonblank entry
  by meaning. Do not introduce a whitelist of recognised processes, room names,
  abbreviations or acceptable phrasings. Examples illustrate the requirement;
  they are not an exhaustive vocabulary. Without AI, content assessment is manual.
  For computer-only projects, identify a computer workstation or workspace
  (e.g. computer labs, a library workspace, home office or PC at home). Bare
  "home" and generic "Design/Simulation" are insufficient and require correction.
  Accept equivalent descriptions by meaning, not a whitelist. The Area/Activity
  entry itself must give the workspace/setup or a specific process/procedure;
  do not borrow missing specifics from other answers. Confirm computer-only work
  from actual RA and ethics activities, including any conditional physical work, not the project
  title. Missing or ambiguous activity evidence requires manual review. Blank
  Area/Activity remains an issue. Keep the activities–facilities check separate.
  Generic "Engineering laboratories" plus an institution/city and computer
  facilities is insufficient for planned physical work, including conditional
  testing. Require a named lab/room or specific process/procedure in Area/Activity
  itself. For confirmed computer-only work, the university computer facilities
  are sufficient; unused lab wording must not force a physical-lab requirement.
- Activities–facilities consistency is a separate check against actual RA and
  ethics activities. Distinguish simulation from planned physical work, including
  conditional work. Require verifiable workspace and activity evidence; handle
  field labels without rejecting otherwise exact quotes. Do not infer activity
  from the project title or certify room suitability.
  Evidence-backed clear missing or incompatible workspace findings are issues
  requiring correction. Reserve manual review for borderline/ambiguous comparisons
  or unverified evidence; extraction and AI verification failures alone are not
  student errors.
- Blank administrative answers and unchanged Y/N options are unanswered (issue),
  not merely ambiguous. Uninterpretable answers require manual review. Retained
  options with an answer misplaced in a reference field remain a completion
  concern; do not silently accept the placement to clear a warning.
  A clearly highlighted single Y or N is a selected answer. Retain the original
  wording and identify the interpreted highlight in evidence. Both/partial/unclear
  marks require manual review; highlighted specialist Yes still needs document
  review. Highlights outside the primary answer options do not select an answer.
- Signatures may be typed or embedded images. Check presence, never authenticity;
  show available images with supporting evidence and deduplicate repeated source
  extracts. Do not let AI entry-quality comments override dedicated sign-off checks.
  PDF images may establish presence only when clearly associated with the signature
  field by placement. Exclude page branding and distant/ambiguous images; display
  the extracted image as evidence without OCR or handwriting/authenticity claims.
  A readable PDF signature field verified to be blank is an issue. Possible
  unrecognised images, drawn ink, annotations or unreadable field areas remain
  manual; do not label an unverified signature as definitely missing.
- Job titles identify roles: Student or an equivalent student role for students,
  and a staff role for supervisors. Project titles in job-title fields are issues
  requiring correction. Assess other role descriptions by meaning, not a whitelist;
  reserve manual review for borderline cases.
- AI entry quality assesses the meaning and placement of populated answers.
  Keep required-field omissions with their dedicated completion checks; do not
  duplicate a missing ethics supervisor name or other required blanks here.
  Assessor identity belongs only to Assessor is student; do not duplicate it in
  entry quality by calling a staff/supervisor name a wrong-field entry.
- Preserve the agreed Low Risk ethics requirement and other completion rules
  documented in the README. Final risk scores must be strictly below initial
  scores; this rule does not establish that scores or controls are appropriate.
- Initial and post-control severity/likelihood may differ. Exclude risk-rating
  calculations and multiplier comparisons from AI entry-quality findings; keep
  rating completion and score reduction with their dedicated deterministic checks.
  Whether a reduction is justified remains for the supervisor to assess.
  A final score alone is valid; do not require a multiplication expression.
- Keep substantive safety adequacy with the supervisor. A complete result is not
  safety approval. A deficient signed document does not establish legal liability.
- Explain whether a result reflects an omission, an uninterpretable entry,
  unverified AI evidence or a missing AI assessment. Do not describe completed,
  disabled or failed processing as still running or pending.

## Planned student experience

If asked to implement the student version, exclude supervisor sign-off checks
and internal moderator decisions/notes. Keep applicable student-owned fields,
signatures and completion checks. Students write their own answers; use
explanations and targeted questions to support revision and judgement. Do not
generate a completed hazard/control plan for unquestioning acceptance. Guided
completion remains an option to evaluate, not an established learning benefit.

## Development and evaluation

- Use the four current examples as development cases. Preserve original first
  submissions and record staff-agreed expected findings and changes to the tool.
  Recheck the other cases when fixing one; do not treat these tuned cases as
  independent validation evidence.
- Keep unfamiliar validation submissions separate from development. Do not tune
  against them and then claim they remain a held-out evaluation set.
- Use synthetic or anonymised fixtures in source-controlled tests. Mock AI in
  routine tests; do not make paid live API calls as part of routine verification.
  Automated tests verify implementation, not live model accuracy or student learning.
- For the baseline, count staff-confirmed correction-required first submissions
  against a defined denominator. Tool flags and manual-check statuses alone are
  not failures. Validate passed cases as well as flagged cases, and retain false
  positives, missed errors and unresolved judgements.
- Record software, rubric, prompt, model and guidance versions for evaluation.
  Staff validation and independent second review are research work to perform,
  not accomplishments to assume. Distinguish document quality from learning;
  later learning measures should include an unaided unfamiliar task. Interviews
  are optional.

## Data and saved reviews

- Never include student names, IDs, signatures, source documents, private review
  JSON, API keys or `.env` contents in committed code, examples or public outputs.
  Follow institutional authorisation, retention and research data-use arrangements.
- Preserve original files, moderator overrides, notes and history during saved
  review refreshes. Keep original automated findings where needed for audit.
  Saved review updates should be idempotent and should not silently start AI calls.
- Keep operational moderation and current H&S follow-up separate from optional
  research participation. Do not assume routine processing authorises research reuse.

## Verification

Use the existing Windows virtual environment. Run relevant tests and checks for
behaviour changes; documentation-only edits need content and diff review rather
than new tests. Standard commands are in the README. If sandbox permissions block
pytest's default temporary directory, use a fresh, explicitly permitted
`--basetemp` path with `-p no:cacheprovider`; do not reuse or delete unrelated paths.

Keep the README accurate when changing behaviour or implemented scope. Keep
proposals, independently validated findings and demonstrated learning outcomes
distinct. The linked Notion project holds the working research brief and decisions.

Latest-attempt selection must use submission metadata timestamps, never filesystem dates. Retain originals, earlier attempts, decisions and history. Keep every attachment of a selected attempt. Missing timestamps or tied latest attempts require retention and a warning; changing selection must not silently run AI.

Specialist-assessment Yes answers require Supervisor check (supporting assessment follow-up), not a student error. Blank/unchanged primary Y/N answers remain issues; unreadable or ambiguous answers need moderator review. Saving Supervisor check counts as moderated feedback and must not cycle through Save and open next. Preserve saved decisions and acknowledgements when relabelling unchanged follow-up evidence.

When Area/Activity is blank, skip activities–facilities consistency entirely, including the AI response schema, retry counts and moderation queue. Keep the missing-field issue with Specific area or activity. Skipped is not a pass; preserve prior findings and decisions for audit.

Risk table completed covers only the activity/equipment/materials, hazard, persons at risk and controls. Rating omissions belong to Risk ratings completed with exact row/field instructions. Skip score reduction when missing numeric values prevent comparison, while retaining any independently verified nonreducing score finding.

Generate eLP feedback only when processing and relevant AI work are finished, all checks requiring confirmation are moderated and remaining moderator judgements are resolved. No draft before completion. Use final outcomes, consolidate duplicate corrections, separate supervisor follow-up, never auto-copy internal notes or unverified AI/extraction claims. Require explicit public wording for overrides without a clear correction. Preserve feedback history and block stale generation/copy; do not send to eLP automatically.

Bulk feedback must use the active attempt selection and the same completion/wording gates as individual feedback. Preserve current edited text, exclude unfinished cases without drafts, keep exclusions separate from downloadable feedback, and verify each copy/download is current. Repeated bulk generation must not duplicate feedback history.

The standard Excel Snapshot ends with an eLP feedback column containing only current generated feedback. Leave unfinished, stale or ungenerated feedback blank. Bulk Excel download uses the same workbook and active attempt selection; do not generate feedback during export or copy internal notes into that column. Preserve full text and line breaks rather than silently truncating Excel cells.

Validation is the default review mode. Routine moderation bypasses individual confirmation only for explicitly approved criterion/source pairs with matching checking/model provenance and clear issue or supervisor outcomes. Never auto-approve checks based on tests or repeated tuning. Unknown versions, overrides and uncertain outcomes still require review. Keep automatic acceptance distinct from human review. Preserve independent audits, original automated snapshots and settings history; changing mode or approvals must not run AI. Feedback gates and queues must share this policy.

Ethics word limits is a disabled reminder, not an assessed criterion. Keep it visible but exclude it from audit answers, comparisons, moderation requirements, overall outcomes and feedback, including legacy saved issues/overrides. Preserve old records; do not count words or start AI to refresh this reminder.
