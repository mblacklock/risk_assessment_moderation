# V2 evaluation findings

Evaluation decisions completed: **18 November 2026**. Branch: `validation-v2`.
Checking fingerprint:
`207e519c3f655d4daca6aecc8abc29e429f5e80a7807486e37489c3d89d27eb2`.
The evaluated AI source used `gpt-5-mini`.

## Scope and decision policy

The independent audit covered **20 selected student submissions** and **24 active
criteria**, giving **480 potential criterion-level check instances**. A submission
may contain more than one document or RA section. The ethics word-limit reminder
was excluded from active checks. This document summarises the subsequent staff
review of disagreements; identifiable records and original documents remain private.

Approval accepts the evaluated source's definite outcomes for this checking version.
An acceptable referral for human judgement does not prevent approval. An incorrect
definite Pass, Issue found or other definitive disposition prevents approval until
the relevant behaviour is fixed and re-evaluated. Approval does not require every
case to be automated, and does not certify all generated feedback wording.

**Approval and recommended improvements are separate decisions.** A check can be
approved while extraction, feedback or referral-reduction improvements remain open.
Approvals are specific to the criterion, source and checking version/model. They do
not transfer automatically to changed checking behaviour or establish correctness
on untested cases. Substantive safety adequacy remains the supervisor's responsibility.

Original audit answers, automated snapshots and evidence were preserved. Staff
corrections were appended as adjudications. Initial agreement and accepted outcomes
after adjudication must be reported separately: the initial human audit is not an
infallible answer key. Counts on the comparison page may incorporate adjudication
classifications; consult the preserved snapshots for initial agreement.

## Approval decisions

**19 criteria approved, one partly approved, four unapproved.** There are 21 approved
criterion/source combinations: Ethics responses has both Rule and AI approval.

| Criterion | Approved source | Notes |
| --- | --- | --- |
| Document readable | Rule | All 20 definite outcomes matched; unreadable-document defect detection was not established by this sample. |
| Assessor is student | Rule | All 16 definite outcomes matched; uncertain name variants remain manual. |
| Project details | Rule | All 20 definite outcomes matched; missing-field detection needs additional coverage. |
| Example row removed | Rule | All 20 definite outcomes matched; retained-example defect detection needs additional coverage. |
| H&S hazards only | AI | All 15 definite outcomes matched; five total referrals remain manual, including two Rule fallbacks without definite-outcome validation. Earlier objections to two referrals were superseded under the clarified policy. |
| Risk ratings completed | Rule | Accepted after correcting audit ownership/missed missing scores; three manual referrals remain. Extra guidance-row/count messages still need improvement. |
| Controls reduce risk rating | Rule | Accepted after identifying audit misses and category mapping errors; three manual referrals and one prerequisite skip remain. Extra guidance-row/count messages still need improvement. |
| Administrative questions | Rule | All 16 definite outcomes matched; four referrals remain manual. |
| Specialist assessments | Rule | All six definite outcomes accepted after correcting one audit selection to Supervisor check; 14 referrals remain manual. |
| Supervisor risk sign-off | Rule | All 18 definite outcomes matched; two uncertain PDF signatures remain manual. |
| Ethics information table | Rule | All 20 definite outcomes matched, including missing/incomplete information findings. |
| Low Risk ethics only | Rule | Accepted after visually confirming that an audit failure had missed the selected Low Risk box; missing-form dependency is skipped. |
| Ethics responses | AI and Rule | Applicable definite outcomes agreed; the missing ethics form is handled by its owning check. Negative-case coverage is limited. |
| Student declarations | Rule | All 19 applicable definite outcomes matched; one missing-form skip. |
| Risk assessment confirmed | Rule | All 19 applicable definite outcomes matched; one missing-form skip. |
| Student ethics sign-off | Rule | All 16 definite outcomes matched; three signature referrals and one missing-form skip. |
| Supervisor ethics sign-off | Rule | All 16 definite outcomes matched; three signature referrals and one missing-form skip. |
| Tutor checklist | Rule | Accepted after visual checks corrected missed empty boxes and an audit concern assigned to the wrong criterion. |
| Supervisor confirmation | Rule | Accepted after visual checks confirmed two empty confirmation boxes missed by the audit. |

| Partly approved / unapproved criterion | Decision and reason |
| --- | --- |
| Specific area or activity | **Rule approved; AI unapproved.** Clear blank-field Rule issues were correct. AI incorrectly accepted insufficient physical-work workspace descriptions by borrowing activity descriptions elsewhere. The Area/Activity entry must itself make the approved area/activity identifiable. |
| Activities–facilities consistency | **Unapproved.** Definite dispositions included passing cases that should wait for workspace clarification and skipping an established workshop/testing incompatibility. Computer-work comparisons were also unnecessarily skipped. Raw Pass/Fail agreement alone concealed these disposition problems. |
| Risk table completed | **Unapproved.** Two definite false issues arose from a PDF row continued across pages and a guidance-only Word row treated as a hazard row. Staff accepted all 20 tables for this criterion; genuine incomplete-table detection is not established by this sample. |
| Student risk sign-off | **Unapproved.** One definite missing-signature finding was false: the original Word document visibly contains a handwritten student signature. The other 17 definite decisions matched; two manual referrals are acceptable. |
| Appropriate field entries | **AI unapproved.** Adjacent PDF Area/Activity and Assessment Title cells were merged, creating a false wrong-field issue. The other disputed definite finding, inconsistent years, was confirmed correct and recorded as an audit miss. Three referrals are acceptable; Rule fallback has no definite pairs to approve. |

## Agreed interpretation

- The standard template has **Area/Activity**; a separate Location field is not
  required. A technician should not have to reconstruct approval of physical work
  by searching the entire document. A recognised workshop may satisfy identification
  while failing the separate activity/facility compatibility check.
- Use the staff-confirmed nomenclature in [LAB_SPACES.md](LAB_SPACES.md).
  Ellison C- and E-block rooms count as laboratories at the broad space-type level;
  SAN and The Zone are IT spaces. The recognised metal-fabrication workshop is not
  a testing space. Do not verify exact equipment or room capabilities.
- Where no usable physical-work space is identified, Specific area or activity
  owns the correction. Facilities comparison should defer/skip rather than invent
  compatibility or duplicate that correction. Missing ethics forms similarly skip
  dependent checks and retain the form-level issue.
- Specialist Yes answers identify **Supervisor check**, not automatically a student
  completion failure. Accepting answer placement must retain Yes-related follow-up.
- Clear project/data-only consequences are not H&S hazards. Borderline wording and
  safe referrals remain acceptable. More direct routing of clear cases is an
  improvement recommendation, not a condition of the current H&S approval.

## Priorities for the next checking version

The implementation checklist is in [TODO.md](TODO.md). These are recommendations,
not changes to the frozen evaluated behaviour.

1. **Correct false field-presence and row findings.** Preserve PDF cell boundaries;
   recognise visible Word signatures at their displayed location rather than only
   their drawing anchor; associate genuine PDF page continuations; exclude
   guidance-only rows from completion and rating instructions.
2. **Correct workspace decisions.** Apply the agreed identification/compatibility
   ownership and broad-space nomenclature; retain separate RA-section associations.
   Avoid unsupported passes and inappropriate skips. Do not require a new template
   field or verify individual room equipment.
3. **Reduce unnecessary referrals in approved checks.** Restrict specialist
   risk-table exclusion to actual hazard rows, parse explicit Yes/No answers with
   explanations, handle administrative questions per RA section, and recognise
   readable rating notation and uncertain image signatures more reliably.
4. **Improve feedback precision and routing.** Remove spurious row instructions;
   explain the precise uncertainty; optionally route clearly non-H&S entries more
   directly while preserving genuine borderline judgement and supervisor duties.

Retest fixes with synthetic layouts and meaningful positive/negative cases, then
evaluate changed checks on fresh independent submissions. Do not hardcode student
identities or use the audited batch as the sole evidence of generalisation. Carry
forward unresolved cases and approved-check improvements without silently
transferring approvals to a new checking fingerprint.

## Interpretation and limitations

Potential criterion instances, explicit moderator confirmations and actual staff
moderation time are different measures. The previous workflow was holistic document
review: several fields could be verified in one quick visual scan. Opening,
interpreting and recording an individual tool finding may take longer than that
scan. This review therefore does **not** establish a reduction in staff time or
workload, nor universal accuracy from a 20-submission sample.

The tool caught genuine audit misses, including absent selections, missing numeric
ratings, non-reducing scores and a year inconsistency. Staff review also found tool
errors and audit category/selection mistakes. These are observed examples, not an
independent measurement of general improvements in consistency, error detection,
auditability or feedback quality. Those remain potential benefits requiring suitable
evaluation. Approval with limited negative-case coverage is a scoped staff decision,
not proof of sensitivity to every possible defect.

Full-class v2 confirmation requirements **have not yet been measured**. V1's 571
pre-approval and 464 post-approval confirmations cannot establish a v2 improvement.
Apply the current v2 approvals to a preserved full-class result and report total
confirmation requirements, reviewed and remaining confirmations, manual/uncertain
cases, supervisor follow-up and unapproved definite findings separately. Record the
checking fingerprint and approval configuration. Measure workflow time independently
if claiming time savings; do not equate 480 potential sample checks or 2,544
full-class potential checks with separately recorded decisions in the old workflow.
