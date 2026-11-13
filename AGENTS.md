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
- Area/Activity must identify a clear manufacturing process, test procedure or
  named room/laboratory. Rules check presence; AI assesses every nonblank entry
  by meaning. Do not introduce a whitelist of recognised processes, room names,
  abbreviations or acceptable phrasings. Examples illustrate the requirement;
  they are not an exhaustive vocabulary. Without AI, content assessment is manual.
- Activities–facilities consistency is a separate check against actual RA and
  ethics activities. Distinguish simulation from planned physical work, including
  conditional work. Require verifiable workspace and activity evidence; handle
  field labels without rejecting otherwise exact quotes. Do not infer activity
  from the project title or certify room suitability.
- Blank administrative answers and unchanged Y/N options are unanswered (issue),
  not merely ambiguous. Uninterpretable answers require manual review. Retained
  options with an answer misplaced in a reference field remain a completion
  concern; do not silently accept the placement to clear a warning.
- Signatures may be typed or embedded images. Check presence, never authenticity;
  show available images with supporting evidence and deduplicate repeated source
  extracts. Do not let AI entry-quality comments override dedicated sign-off checks.
- Preserve the agreed Low Risk ethics requirement and other completion rules
  documented in the README. Final risk scores must be strictly below initial
  scores; this rule does not establish that scores or controls are appropriate.
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
