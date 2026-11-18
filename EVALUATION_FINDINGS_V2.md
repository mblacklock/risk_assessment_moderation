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

## Full-cohort operational results — 18 November 2026

This is a separate operational snapshot of **All v2**, not an extension or revision
of the 20-submission independent validation. The saved batch contains **106 selected
submissions (latest attempts)**, with **24 active criteria per submission**. It is
finished processing, has AI enabled, and uses **Moderate submissions** (`routine`)
with the current global approvals.

| Dashboard measure | Recorded result |
| --- | ---: |
| Potential criterion-level check instances: 106 × 24 | 2,544 |
| Checks requiring explicit confirmation | 304 |
| Required confirmations reviewed | 0 of 304 |
| Required confirmations remaining | 304 |
| Validated findings accepted automatically | 220 |
| Submissions provisionally classified Fail — correction required | 94 |
| Submissions classified Needs moderator review | 12 |
| Submissions classified Pass | 0 |
| Submissions classified Pass — supervisor follow-up | 0 |

The 12 dashboard Needs moderator review outcomes comprise four saved `review` and
eight `moderator` outcomes. These are submission-level classifications, whereas
304 and 220 count criterion-level findings. A confirmation requirement can arise
from an unapproved definite finding as well as an uncertain/manual referral; 304
is not a count of uncertainty alone. The 220 automatically accepted findings bypass
individual confirmation under staff-approved criterion/source rules; they are not
220 independently verified student errors or 220 reviewed confirmations.

### Comparison with v1

| Stage | Checks requiring confirmation |
| --- | ---: |
| V1 before approvals | 571 |
| V1 after approvals | 464 |
| V2 after approvals | 304 |

- **2.87 explicit confirmations per submission:** 304 ÷ 106 = 2.8679.
- **160 fewer than approved v1:** 464 − 304 = 160; 160 ÷ 464 = **34.5% reduction**.
- **267 fewer than pre-approval v1:** 571 − 304 = 267; 267 ÷ 571 = **46.8% reduction**.
- **88.1% reduction against the theoretical maximum:**
  (2,544 − 304) ÷ 2,544 = 88.0503%. The remaining 304 represent 11.9% of potential
  criterion-level instances. This theoretical denominator is not the number of
  separately recorded decisions made in the previous holistic manual workflow.

Percentages are rounded to one decimal place; the per-submission average is rounded
to two. The v1–v2 difference reflects **both changes in checking behaviour and
differences in approved criterion/source combinations**. It must not be attributed
wholly to increased checking accuracy.

### Saved provenance and approval configuration

The batch was created at `2026-11-18T15:00:50.087273+00:00`; its saved `updated`
value at inspection was `2026-11-18T15:56:34.548397+00:00`. These are stored batch
timestamps, not a staff-time measurement or an inferred processing duration.

All **2,544 active saved findings** carry the current checking fingerprint:
`207e519c3f655d4daca6aecc8abc29e429f5e80a7807486e37489c3d89d27eb2`.
The 21 active global approvals carry that same fingerprint and were recorded on
18 November 2026. The saved AI model field is `gpt-5-mini` for 103 selected
submissions; it is **not recorded for three**. No missing per-submission model
provenance has been inferred or filled in.

The private shared registry is `reviews/global-approvals.json`. At inspection its
revision was `b574e8dd-c30d-4c35-aa70-19dce0fbe54d`, and its SHA-256 was:
`14da59439b77807f8cd15b47005de97709b615d44d29d7172b2d2c99f04eb28a`.
This identifies the inspected configuration, rather than asserting that the mutable
registry can never change. Its private evidence, origin records and change history
are retained locally; they are not copied into this public summary.

The relevant active **21 criterion/source combinations** were:

| Source | Approved criterion IDs |
| --- | --- |
| Rule (19) | `admin`, `declarations`, `ethics_details`, `example`, `identity`, `location`, `low_risk`, `narrative`, `physical`, `project`, `ratings`, `readable`, `risk_reduction`, `specialists`, `student_ethics`, `supervisor_ethics`, `supervisor_ra`, `supervisor_statement`, `tutor` |
| AI (2) | `hs_relevance`, `narrative` |

These correspond to the approval decisions described above: 19 fully approved
criteria, Rule-only approval for Specific area or activity, and four unapproved
criteria. Uncertain findings, overridden results and findings without matching
checking provenance still require confirmation. Validation mode continues to
require its independent review process; this operational batch uses routine mode.

### Interpretation and safeguards for this operational snapshot

Potential check instances, required confirmations, confirmed student errors and
actual moderation time are distinct. **The 94 Fail outcomes are provisional and
have not all been independently moderated.** With zero of the 304 required
confirmations reviewed in this batch, the dashboard totals are not a verified count
of student errors, error prevalence, or final eLP decisions. A submission can have
multiple findings, and automatic acceptance is a policy decision supported by the
earlier evaluation rather than a new independent adjudication of each finding.

This snapshot demonstrates reduced **explicit confirmation requirements** under
the recorded configuration. It does **not** measure reductions in staff workload,
moderation time or checking error rates. The previous workflow involved a holistic
document scan; the time needed to open, interpret and record a tool finding can
differ from the time to verify several fields visually. Comparative time and error
studies would be needed for those claims. No new independent accuracy estimate is
established by running the full cohort.

The original 20-submission v2 audits, automated snapshots, adjudications, approval
decisions and histories remain unchanged. This documentation update did not rerun
AI, change rules or approvals, or generate student feedback. Substantive safety
adequacy remains the supervisor's responsibility.

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

Full-cohort confirmation requirements under the current v2 approvals are recorded
in the separate operational-results section above. Staff time and workload savings
remain unmeasured. Do not equate potential criterion instances with separately
recorded decisions in the previous holistic review workflow.
