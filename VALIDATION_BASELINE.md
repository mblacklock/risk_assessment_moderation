# Validation baseline v1

**Frozen evaluation reference: 17 November 2026 (Europe/London).**

Git tag: `validation-baseline-v1`. The commit identified by this tag is the fixed
code, rubric, prompt and guidance baseline. This is a local moderator-tool version,
not a public deployment or a claim that the checks have been independently validated.

## Recorded configuration

- Configured OpenAI model: `gpt-5-mini`.
- Checking/model fingerprint: `8ac647d91c9d5c4f56eeace47d11988742e7baa53fb546169103459d82aeb7c5`.
- Python: `3.13.0`; platform: Windows.
- Rubric/check definitions: `moderation/criteria.py` and `moderation/checks.py` at the tag.
- AI instructions and verification: `moderation/ai.py` at the tag.
- Guidance and operating scope: `README.md` and `AGENTS.md` at the tag.
- Dependency pins: `requirements.txt` and `requirements-dev.txt` at the tag.
- Private review configuration and per-finding provenance remain in local review records; they are not committed.
- A model alias can change externally. Record any provider/model configuration changes during evaluation.

## Installed package versions

| Package | Version |
| --- | --- |
| Django | 5.2.19 |
| openai | 3.49.0 |
| python-docx | 1.2.0 |
| PyMuPDF | 2.1 |
| openpyxl | 3.1.5 |
| python-dotenv | 1.2.4 |
| pytest | 9.2.0 |
| ruff | 0.17.4 |

## Recorded file fingerprints

SHA-256 of the files in this Windows workspace when the baseline was recorded.
The Git tag is the full repository reference; these hashes identify the local
guidance, rubric, prompt and dependency files. Line-ending changes can alter byte hashes.

| File | SHA-256 |
| --- | --- |
| `README.md` | `28a3049e6e6043a58a31064c49ba18300058fc153879f2d074c067f44719ed91` |
| `AGENTS.md` | `80a858ccfabaa05fe79b9460a9ab3ca4b61b494ae5b93cb00a62f8265dbada1e` |
| `moderation/criteria.py` | `6c4e3dab5c2fc4d7a1b5c82ae3819dd16569264e8098a2c726e2501ed69da1a0` |
| `moderation/checks.py` | `90968c97286039e3c1bca80a94824bb0a02dfdf9faba22cc46baab33c36fe6eb` |
| `moderation/ai.py` | `19e748c446c5237f99fccbbd9eb0b31f12e51d2c06eae29d72c7c5f771f832c6` |
| `requirements.txt` | `0517f664e13f8f69fd2defc3ea545489faebb268d74782078b83fdf25881a24e` |
| `requirements-dev.txt` | `c2a76233f465c0f4d05f068583e3333dc3b8f954280b3c50bef8e4c9319d917b` |

## Verification at freeze

- 365 Python tests passed.
- 10 JavaScript workflow tests passed.
- Django system check, Ruff lint/format checks and Git diff checks passed.
- Routine tests used synthetic fixtures and mocked AI, with no paid live AI evaluation.

## Evaluation procedure

1. Use unfamiliar submissions; retain the previously tuned examples as development cases.
2. Select and record the evaluation sample and denominator before inspecting tool results.
3. Audit original submissions independently, including cases the tool passes. Save the full batch before revealing comparisons.
4. Compare against the saved original automated outcomes. Retain discrepancies, uncertainty, source/version/model information and a defined independent second-review subset.
5. Record findings before changing code, prompts, rubric or guidance. Put fixes in a later version; do not retune this baseline on evaluation cases.
6. Treat agreement statistics as descriptive comparisons, not automatic validation or evidence of learning. Approve checks explicitly only when the agreed evidence supports that decision.

## Preserved scope and limitations

- 24 active completion/consistency checks plus the inactive ethics word-limit reminder.
- Validation mode keeps flagged findings for confirmation. Routine moderation bypasses individual confirmation only for explicitly approved, matching-version/source clear findings; uncertainty still requires review.
- Feedback is generated only when its processing, review and public-wording requirements are satisfied. Nothing is sent to eLP automatically.
- Originals, earlier attempts, decisions, audit snapshots and histories remain private local files. This commit does not publish them or authorise research reuse.
- Substantive safety adequacy remains with the supervisor. The student-facing checker and guided completion are proposals.
- Accuracy, workload savings, independent validation and learning outcomes remain to be evaluated.

## Returning to this baseline

Inspect the tag `validation-baseline-v1` or check it out in a separate worktree.
Do not reset or overwrite private reviews to return to a code version. Retain the
original environment and private evaluation records under institutional data-use
and retention arrangements. Changes after this tag belong to a new documented version.
