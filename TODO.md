# TODO

## After v2 evaluation — 18 November 2026

See [EVALUATION_FINDINGS_V2.md](EVALUATION_FINDINGS_V2.md) for the completed
20-submission evaluation, source-specific approvals and limitations. There are
19 approved criteria, one partly approved and four unapproved. Acceptable manual
referrals do not block approval; incorrect definite outcomes do. Recommended
improvements may remain open for approved checks. Preserve the evaluated v2
fingerprint, original audits, tool snapshots and adjudications; implement changes
in a later checking version and do not automatically transfer approvals.

### Priority 1 — false findings and unsafe automatic dispositions

- [ ] Preserve adjacent PDF cell boundaries for Area/Activity and Assessment Title.
  Prevent merged extraction from creating a false wrong-field issue. Keep real
  misplaced/contradictory entries detectable. Re-evaluate AI field-entry quality.
- [ ] Associate floating/anchored Word signature images with their displayed
  sign-off field. Fix the observed false missing student RA signature; preserve
  genuinely blank fields and manual fallback for uncertain presence. Re-evaluate
  Student risk sign-off. Presence detection does not authenticate a signature.
- [ ] Join genuine PDF risk-row continuations across page breaks without inventing
  a new incomplete row or borrowing fields from unrelated activities. Verify both
  valid continuations and genuinely missing fields. Re-evaluate Risk table completed.
- [ ] Exclude guidance-only/footer rows from assessed hazards and from numeric
  rating/reduction instructions. Preserve genuine incomplete rows and multi-rating
  ambiguity. Remove spurious row/count correction messages even where the overall
  rating issue is correct. Risk table approval remains withheld; rating completion
  and reduction are approved with this feedback/parser improvement still open.
- [ ] Make AI Area/Activity decisions follow the staff-agreed identification rule:
  planned physical work needs an immediately identifiable area/activity in that
  entry; descriptions elsewhere do not repair a vague entry. Retain the agreed
  computer-work interpretation. Do not require a new Location field in the standard
  template. Rule blank-field decisions are approved; AI decisions remain unapproved.
- [ ] Refine facilities comparison and prerequisites: defer when the workspace
  is unidentified; compare separately assessed sections in context; identify
  genuine broad space-type incompatibilities; avoid unnecessary computer-work
  skips. Apply [LAB_SPACES.md](LAB_SPACES.md), including Ellison C/E laboratories,
  SAN/The Zone IT spaces and the fabrication-workshop testing restriction. Do not
  check exact room equipment or silently canonicalise unconfirmed room prefixes.
  Re-evaluate Activities–facilities consistency.

### Priority 2 — reduce referrals in approved checks

- [ ] Restrict specialist-question exclusion to actual hazard rows, rather than
  excluding questionnaire cells because their enclosing Word table also contains
  risk headings. Recognise the questionnaire without inferring answers from hazard
  narrative. Preserve ambiguous-answer review and all Yes-related supervisor work.
- [ ] Parse explicit administrative Yes/No answers followed by explanations,
  including answers appended after retained template options. Assess each RA's
  questions separately when several RAs are supplied. Do not infer an answer from
  unchanged options or treat unreadable/missing questions as passed.
- [ ] Improve readable rating notation handling, including parenthesised scores,
  expanded severity/likelihood descriptions and trailing band words. Preserve
  ambiguous pairing and real missing scores; apply consistent parsing to reduction.
- [ ] Improve PDF image/drawing signature-presence detection across RA and ethics
  sign-offs. Keep safe manual referrals when uncertain; do not turn them into false
  missing-signature findings. Current approved sign-off checks need not await this.

### Priority 3 — precision and evaluation follow-through

- [ ] Improve H&S routing at individual-entry level: optionally give direct
  correction findings for independently clear project/data-only hazards while
  retaining judgement for genuine H&S mixtures. H&S approval remains valid for the
  evaluated fingerprint; acceptable referrals are not definite decision errors.
- [ ] Keep correction wording specific, evidence-backed and owned by the appropriate
  check. Do not duplicate location, ratings or missing-form corrections in dependent
  checks. Do not certify extraneous guidance-row instructions merely because an
  overall Issue found is correct.
- [ ] Evaluate changed checks using targeted synthetic regression fixtures and
  fresh independent submissions, including real defect cases where the v2 sample
  contained only passes. Do not hardcode sample identities or transfer approvals.
- [ ] Measure full-class v2 confirmation requirements under the recorded approval
  configuration without rewriting original evaluation records. Distinguish required,
  reviewed and remaining confirmations, uncertain referrals, supervisor follow-up
  and unapproved definite findings. Measure staff time independently if claiming
  workload or time savings.

## Historical v1 implementation list

The completed items and hold statements below describe the v1-to-v2 implementation
stage. They are retained as history; current v2 approval decisions are in the
evaluation summary above and supersede earlier statements that a check is on hold.


## After validation baseline v1

Keep checking changes out of the frozen evaluation baseline. Implement and test
these in a later version; preserve the original evaluation findings.

Implementation completed on `validation-v2` on 17 November 2026. Checked
items below describe implemented moderator behaviour or explicitly recorded
conditional future requirements. They do not constitute new staff validation or
automatic approval of changed checks. Frozen findings, audits and approvals were
not rewritten. Remaining uncertain extraction, section/field association and
semantic judgements deliberately retain manual review. The student application
has not been implemented.

- [x] Improve assessor-name matching when the student includes extra middle names.
  Consider accepting an entered name when the first name and surname match the
  submission identity, despite additional middle names. Preserve sensible handling
  of compound and hyphenated surnames. Do not treat a shared first name alone as
  sufficient evidence of identity.
- [x] Keep shortened first names or other ambiguous variants subject to manual
  review unless corroborating document evidence establishes the match. Do not
  introduce a whitelist of student names or automatically assume nicknames match.
- [x] Verify any revised matching with synthetic cases covering extra middle
  names, compound surnames, shortened names and conflicting student/supervisor
  names. Retain uncertain outcomes where the evidence does not establish identity.

The current **Assessor is student** rule has been approved for definite outcomes
in the audited batch. Its uncertain matches still require moderator review.
These proposed improvements are not prerequisites for that scoped approval.

- [x] Prevent blank project fields from borrowing text from the next section.
  A blank Assessment Title must not be populated from a following risk-table
  heading such as “Risk Rating”. Preserve layout/field boundaries and verify
  blank fields, next-section headings and genuine multi-line answers with
  synthetic fixtures. Retain the frozen evaluation result; approval of Project
  details is on hold pending a later-version fix and re-evaluation.

## Area/Activity findings to address after evaluation

- [x] Align computer-work guidance with the agreed interpretation: a clear
  computer-based activity description can be sufficient for a computer-work RA
  section without requiring a named workstation or room. “Computer Software
  Based” was accepted in the evaluated case. Assess meaning, not a whitelist of
  phrases, and keep separately planned physical work and its RA in context.
  This clarification does not establish an institutional exemption from RA.

- [x] Prevent an unsupported assumption that a course/module code identifies a
  room. The evaluation found a module code incorrectly accepted as a named room.
  Assess the meaning and document context; do not hardcode a whitelist or blacklist
  of room names, module codes, abbreviations or acceptable phrases. Retain manual
  review when the evidence cannot establish what a code identifies.
- [x] Investigate extraction and assessment of multiple RA sections in one
  submission. Preserve each Area/Activity entry and associate it with the relevant
  risk rows and activities rather than comparing the first entry with every
  section's work. Distinguish computer work from separately assessed physical
  work while checking the overall RA/ethics consistency. Do not silently ignore
  an insufficient workspace entry or assume the submission should pass after
  correcting the section association. Verify with synthetic multi-section cases.
- [x] Align later-version guidance with the agreed interpretation for alternative
  forms: a dedicated Location field naming the workspace can satisfy the location
  requirement without repeating it under Area/Activity. Adding that field is not
  itself a defect. The biomass assessment was agreed to pass because it explicitly
  identified its laboratory; this does not establish that every broad process
  description is sufficient on its own. Preserve the frozen result and record
  the clarification separately from the initial independent audit.

“Northumbria city campus” has been agreed to be insufficient for the planned
physical work. That case is a human error caught by the tool, not a checker fix;
its agreed classification is recorded privately with the evaluation decisions.


- [x] Refine activities–facilities consistency to flag genuine conflicts between
  activities and facilities. Keep absent or insufficient location descriptions
  with Specific area or activity rather than repeating the same correction.
  Apply the agreed computer-work interpretation and correctly associate separate
  RA sections with their activities. Retain uncertainty where the comparison
  cannot be verified. Approval is on hold pending this later-version refinement.

## Evaluation reporting

- [x] Add agreed classifications to the comparison results and per-check statistics:
  human error caught by the tool, tool error, rubric/interpretation disagreement,
  or unresolved. Do not assume the initial human audit is an infallible answer key
  or count every disagreement as a tool error.
  Preserve the original independent audit and automated snapshot; report initial
  agreement separately from the findings agreed after examining disagreements.
  Include human errors caught by the tool as positive findings, with case-level
  reasons and the relevant denominators. The earlier batch's private evaluation
  decision log is retained separately; new in-app classifications do not rewrite
  it or silently infer adjudications from existing notes.

## Risk-table completion findings

- [x] Accept clearly associated continuation rows where activity/equipment is
  stated once for a group of hazards. Do not require the same equipment name to
  be repeated in each following row when the relationship is unambiguous.
  Preserve evidence of the parent activity and the continuation rows. Do not
  blindly fill down across unrelated activities, table/section boundaries or
  ambiguous blank cells. Verify clear continuations and genuinely missing entries
  with synthetic fixtures in a later version; keep the frozen finding intact.

- [x] Require Persons at risk to identify a person or group rather than accepting
  a count alone. Numbers-only entries such as “1” or “1–3” do not complete this
  field. Accept meaningful descriptions, including descriptions with counts,
  without a whitelist of roles or names. Verify numbers-only, named people,
  groups, counts with roles and extraction uncertainty using synthetic fixtures.

- [x] Investigate PDF risk-table extraction failures where staff can read completed
  tables. Preserve the manual fallback when extraction remains unreliable, and
  do not turn an unverified extraction gap into a student correction request.

## H&S relevance and future student feedback

- [x] Route borderline mixtures of genuine H&S consequences and minor
  project-related wording to **Needs moderator review**, so a moderator can judge
  whether correction/resubmission is warranted. Clear non-H&S hazards remain
  Issue found; valid H&S entries remain Complete. Do not use this refinement to
  downgrade an evidence-confirmed non-H&S rule flag, which still requires Issue
  found under the agreed rule protection. Retain the frozen automated outcome
  and the distinction between technical wording defects and operational waivers.

- [x] In a later version, identify project-only consequences mixed into an
  otherwise H&S-relevant hazard description. Do not reject genuine health effects
  such as stress or fatigue merely because software problems trigger them.
  Keep the technical rubric finding separate from a moderator's decision to
  waive resubmission for a minor wording point; do not count that waiver as
  evidence the automated technical assessment was correct.
- [x] Record the conditional student self-checker requirement: if implemented, ask students to remove
  project-only consequences, such as milestone delays, while retaining their own
  relevant H&S description. This is a future requirement, not a current feature.

## Rating completion and minor cleanup

- [x] Do not request numeric ratings for wholly unused/N/A rows with no assessed
  activity or hazard. Keep genuine partially completed risk rows subject to the
  existing rating-completion requirements.
- [x] Provide a clear audit/reporting place for corrections outside the current
  check categories, including removal of unused rows. Distinguish written
  feedback already identifying a defect from an audit-selection/mapping gap.
- [x] Keep a minor technical cleanup finding separate from the moderator's
  decision to waive resubmission. Where proportionality needs judgement, present
  the cleanup concern for moderator review rather than mislabelling it as missing
  ratings. Preserve the original technical finding, reviewer reasoning and waiver.

- [x] Accept readable rating formats with the band before the number (for example
  “L – 4” or “L 6”), square-bracket band labels, and a band label wrapped onto the
  next line. Do not split a wrapped label into another rating entry. Preserve
  genuine multi-score rows, ranges and ambiguous entries rather than selecting
  an arbitrary number. Verify normalization with synthetic cases.

- [x] Distinguish technical rating-entry defects from the moderator's decision
  to accept them without resubmission. The agreed examples are a range instead
  of a single rating, an invalid band annotation such as “5 (5)”, and a final
  multiplication expression with no entered result such as “2x1 (L)”. Do not
  silently repair these to clear the student's correction requirement. A numeric
  final score alone is still sufficient; calculations and band labels are optional,
  but any included annotation should be consistent with the form.
  If the proposed student self-checker is implemented, prompt students to correct
  these entries. In moderator use, retain judgement for minor defects that may
  reasonably be accepted. Do not turn PDF extraction failures into student errors.

- [x] Apply the agreed rating-format and unused-row improvements to score-reduction
  comparisons as well as rating completion. Compare all populated valid pairs;
  do not let a wholly unused/N/A row block them. Keep missing numeric ratings
  with rating completion, preserve independent nonreducing-score findings, and
  retain manual review when actual values/pairing cannot be established.

## Yes/No answer formatting

- [x] Recognise a clearly distinguished single primary Yes/No option through
  formatting, including one bold option when the other is not bold. Preserve
  the original wording and interpreted selection as evidence. Compare against
  template formatting and surrounding text; do not infer an answer from both
  bold options, inherited styling or unclear marks. Retain manual review where
  selection cannot be established. Cover Word and PDF representations with
  synthetic fixtures in a later version.

- [x] Recognise equivalent administrative question wording when the intended
  question and its Yes/No answer are clear. Do not require the exact full template
  sentence. Preserve the matched question/answer evidence and retain manual
  review for ambiguous mappings or alternative forms where the required question
  cannot be established. Administrative-question approval remains on hold pending
  wording and selected-option formatting improvements.

## Specialist-assessment feedback

- [x] Distinguish genuinely uninterpretable answers from interpretable answers
  with a completion/format concern requiring moderator judgement. For the latter,
  retain Needs moderator review where appropriate, but explain the specific
  concern instead of asserting no reliable Yes/No answer could be established.
  Preserve the intended primary answer and the associated notes/reference text
  as evidence. A future student self-checker should identify the correction needed;
  a moderator can decide whether to accept the entry without resubmission.

- [x] For intelligible Yes/No answers misplaced below reference prompts with
  unchanged primary options, preserve the technical completion concern. In the
  moderator workflow, allow judgement about accepting the placement; do not
  silently clear it as fully completed. A future student self-checker should ask
  for selection in the primary answer field. Keep any Yes supporting-assessment
  follow-up, even where a moderator accepts the answer placement.

- [x] Preserve and interpret Word run highlighting on primary specialist Yes/No
  options. A single highlighted Y or N is a selected answer even while both
  option letters remain in extracted text. Highlighted Yes retains supervisor
  follow-up. Do not count highlights in reference fields, both-option highlights
  or unclear partial marks as an unambiguous selection. Add synthetic Word cases
  alongside the existing PDF highlight coverage.

- [x] For alternative specialist-assessment documentation, distinguish actual
  questionnaire fields from narrative hazard/control headings. Preserve supplied
  assessment documents and references as evidence, but do not infer unanswered
  categories are unnecessary. Route ambiguous coverage to moderator review and
  retain supervisor assessment of supporting documents. Specialist-assessment
  approval is on hold pending the agreed recognition and interpretation fixes.

## Sign-off field extraction

- [x] Associate floating Word text boxes with the fields they occupy instead of
  treating their text only as paragraphs at the drawing's anchor. Verify field
  association before declaring a job title missing. Preserve original text and
  placement evidence; use manual review if the association is uncertain.
  A project title in a job-title field is present but inappropriate: keep its
  suitability finding with Appropriate field entries rather than duplicating it
  as a missing sign-off field. Test with synthetic floating-text and blank-field
  documents; do not alter the frozen evaluation findings.

- [x] Recognise equivalent name labels within the correct sign-off section on
  alternative templates, such as Name under To be completed by the Line Manager.
  Use section/role context to associate names; do not borrow unrelated names or
  confuse separate assessors. Report missing fields accurately and keep any
  prescribed-template requirement separate from field-presence findings.
  Supervisor risk sign-off approval is on hold pending this compatibility fix.

## Populated field-entry judgements

- [x] Keep valid job-title suitability findings while excluding retained-example
  comments already owned by Example row removed. Avoid duplicate student
  correction messages across checks.
- [x] Apply the agreed multi-RA section boundaries to entry-quality judgements:
  different activities/workspaces in separately assessed sections do not by
  themselves establish contradictory entries. Ensure floating job-title text is
  available to the suitability assessment after its field association is verified.

- [x] Treat unverified supervisor-name variations, including initials and adopted
  English names, as a manual identity-confirmation question rather than a definite
  contradiction. Do not assume matching surnames prove identity or maintain a
  source-controlled list of real staff aliases. Preserve the compared entries
  and let the moderator establish whether they refer to the same person.

- [x] Distinguish a suspected laboratory-code discrepancy from an established
  incorrect entry. Show the conflicting codes and request moderator clarification
  when intended locations are uncertain; after a typo is confirmed, request the
  appropriate correction without guessing the intended room. Do not use a
  whitelist of recognised room codes or assume every additional lab is a conflict.

## Missing-document feedback

- [x] When the ethics form itself is absent, explain that the form is missing
  rather than only listing all header fields as blank. Preserve missing-field
  findings for a supplied but incomplete form. Keep extraction uncertainty
  separate from a verified missing document. Ethics information table is approved
  for the evaluated Rule outcomes; this wording improvement is not a prerequisite.

## Ethics selection and missing-form dependencies

- [x] Improve PDF Low/Medium Risk checkbox recognition while retaining manual
  review for unreadable or ambiguous marks. Do not infer a Low Risk selection
  from template guidance that projects must be Low Risk.
- [x] When an ethics form is verified absent, keep its missing-document issue
  with Ethics information table and avoid duplicate requests to confirm Low Risk
  selections in a nonexistent form. Mark dependent checks as unassessable/skipped,
  not passed. Keep extraction uncertainty separate from verified absence.

- [x] Display definite-outcome coverage alongside agreement statistics, with
  explicit numerators and denominators. For example, 19/19 agreed (100%) and
  19/20 definite outcomes (95% coverage), with one manual case. Keep tool
  coverage distinct from the number of comparable definite audit/tool pairs;
  report uncertainty and skipped cases separately rather than counting them as
  incorrect passes or fails.

H&S hazards only approval is on hold pending the agreed distinction between clear
non-H&S defects and borderline mixed wording requiring moderator judgement.
