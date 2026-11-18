# V1 evaluation findings

Recorded: 18 November 2026 (Europe/London).

Evaluation software reference: Git tag `validation-baseline-v1`, commit
`a77871c0fe9cbe098c12399babd303deafacd00f`. This document is maintained on
`validation-v1`; the frozen tag is unchanged. See
[VALIDATION_BASELINE.md](VALIDATION_BASELINE.md) for the recorded software,
checking/model fingerprint, configuration and evaluation procedure.

## Scope and definitions

The All batch contains 106 selected student submissions. With 24 active criteria,
this gives **106 × 24 = 2,544 potential criterion-level check instances**. The
disabled Ethics word limits reminder is excluded from this denominator.

These measures describe different things:

- **Potential check instances:** every submission/active-criterion combination,
  whether it passes, needs follow-up, is uncertain or cannot be assessed. This is
  a theoretical maximum for separately confirming every criterion; it is not a
  count of independent manual actions previously performed.
- **Checks requiring explicit moderator confirmation:** findings that the
  applicable review policy puts into the confirmation workflow. This includes
  uncertain findings and definite issues/follow-up that have not been accepted
  automatically under an approved, version-matched policy. It is not a count of
  student errors. Confirmations already recorded remain part of the required
  total; the total is not simply the number still unreviewed.
- **Actual staff moderation time:** elapsed staff time spent reviewing originals,
  checking findings and evidence, deciding outcomes, recording decisions and
  preparing feedback. It must be measured using a comparable workflow; it cannot
  be calculated from the confirmation counts below.

Potential instances are counted even where evidence is unavailable or a check is
skipped. A skipped or unassessable check must not be interpreted as a verified
pass merely because it does not add a separate confirmation action.

## Recorded confirmation requirements

| Stage | Checks requiring explicit confirmation | Interpretation |
| --- | ---: | --- |
| Earlier displayed snapshot | 579 | Historical display count; its exact version/configuration is not established in this summary. |
| V1 before applying approved checks to All | 571 | Pre-approval confirmation requirement for the All batch. |
| V1 after applying approved checks to All | 464 | Confirmation requirement after applying the version-specific approvals. |
| V2 | Not yet measured | No v2 confirmation-requirement result is reported. |

The 579 snapshot is retained for transparency. The change from 579 to 571 is not
attributed to a particular checking improvement or used as a controlled version
comparison. The 571-to-464 comparison concerns applying approvals within v1,
rather than a change from v1 to v2.

The theoretical denominator remains 2,544 for the calculations below. The recorded
snapshot counts are operational confirmation requirements, not accuracy estimates
or independent evidence that every automatically accepted result was correct.
Private case-level records and original evaluation findings remain separate from
this aggregate report.

## Calculated results

Percentages are rounded to one decimal place; the per-submission average is
rounded to two decimal places.

| Comparison | Calculation | Result |
| --- | --- | ---: |
| Reduction in explicit confirmation requirements from the theoretical maximum to the pre-approval v1 requirement | (2,544 − 571) ÷ 2,544 × 100 | **77.6%** |
| Further reduction after applying validation approvals | 571 − 464 | **107 checks** |
| Further reduction as a proportion of the pre-approval total | 107 ÷ 571 × 100 | **18.7%** |
| Potential instances remaining subject to manual confirmation after approvals | 464 ÷ 2,544 × 100 | **18.2%** |
| Overall reduction against the theoretical maximum | (2,544 − 464) ÷ 2,544 × 100 | **81.8%** |
| Average explicit confirmation requirements per selected submission after approvals | 464 ÷ 106 | **4.38** |

Automated checking reduced explicit confirmation requirements from 2,544
potential check instances to 571, a 77.6% reduction against that theoretical
maximum. Applying validation approvals reduced the requirement further by 107,
from 571 to 464, or 18.7% of the pre-approval total. Overall, 464 of 2,544 potential
instances remained subject to manual confirmation (18.2%), equivalent to an
81.8% reduction against the theoretical maximum and an average of 4.38 explicit
confirmations per submission.

These are descriptive results for the recorded batch and policy configuration.
They should not be presented as a 77.6% or 81.8% reduction in staff time, workload,
or the number of checks previously performed by a human moderator.

## Interpretation and limitations

### Confirmation requirements and moderation time

The previous manual workflow involved holistic document review, not 24 separately
recorded decisions per submission. A moderator could often verify several fields
through one quick visual scan, while also judging the document as a whole.
Consequently, the 2,544 potential instances are not an observed baseline of 2,544
separate staff actions.

The tool workflow can take longer per confirmation: a moderator may need to open
a finding, inspect its supporting evidence and the original, interpret the
result, select an outcome and record a decision. Opening documents, navigating
between findings and preparing feedback also take time. Counts alone do not
capture those costs, nor do they establish how many confirmations can be handled
together.

The results therefore demonstrate a **reduction in explicit confirmation
requirements, not an established reduction in moderation time or staff workload**.
Comparable measurements of the original holistic workflow and the tool-assisted
workflow, including equivalent feedback preparation, are needed to evaluate time
savings. Any timing observations from a different task, sample or workflow must
be reported separately rather than converted into savings from these counts.

### Potential benefits requiring further evaluation

- **Consistency:** a shared checklist and explicit criteria may make treatment
  across submissions more consistent. This report does not independently
  demonstrate improved consistency or inter-rater agreement.
- **Error detection:** automated checks may draw attention to omissions or
  inconsistencies missed during a visual scan. Aggregate confirmation counts do
  not establish sensitivity, specificity or the absence of false passes and
  false flags; case adjudication and checks of passed cases are still needed.
- **Auditability:** stored findings, evidence and moderation decisions may make
  the basis for feedback easier to inspect. Their availability alone does not
  demonstrate that records are complete, accurate or useful in practice.
- **Feedback quality:** criterion-specific findings may support clearer and more
  consistent correction instructions. Feedback accuracy, clarity, usefulness and
  effects on student revision or learning require separate evaluation.

These are potential benefits, not independently demonstrated outcomes of this
aggregate confirmation-count analysis. The initial human audit is also subject
to error and interpretation differences; disagreements should be examined rather
than automatically assigned to the tool. Development fixes or repeated tuning
are not substitutes for independent validation.

### Version specificity and responsibility

V1 approvals apply to the explicitly approved criterion/source pairs and recorded
checking/model provenance. They are not blanket approvals of every criterion or
uncertain outcome, and **do not automatically transfer to v2**. V2 confirmation
requirements have not yet been measured; no v2 reduction or timing claim is made
here.

The tool assesses completion and internal consistency. Substantive safety
adequacy, suitability of controls and approval of the actual work remain the
supervisor's responsibility. A completion result or automatically accepted
finding is not safety approval.
