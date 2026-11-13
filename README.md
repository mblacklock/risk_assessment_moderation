# Risk assessment moderation

A local Django app for reviewing completion of KB6060 risk assessment and ethics
forms downloaded as a ZIP from Turnitin/Blackboard.

Upload a submission ZIP to run 25 completion checks, inspect a sortable/filterable
matrix, review evidence, record moderation decisions and export CSV or Excel.
The app uses local files and does not need a database.

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
the server and select "Include AI language checks" when uploading. You can also
run AI on an existing review or retry failed AI checks.

AI checks send extracted text to OpenAI, use structured responses, request
`store=False`, and check that quoted evidence exists in the submission. Original
documents are not uploaded to OpenAI. API charges apply. A missing key, failed
request, refusal or unverifiable evidence never counts as an AI pass. Tests mock
the API; live model accuracy must be evaluated using moderated examples.

Without AI, language-based criteria remain manual checks. Fixed rule failures
cannot be waived by AI. A reviewer can override any result with an explanatory
note, while the automated finding is retained. No API key is exposed to the browser.

Debug mode is enabled for local development. The app generates a temporary
development secret if no key is configured. Set a stable private
`DJANGO_SECRET_KEY` and disable debug mode before hosting.

There is no database, Django admin, authentication or database-backed session
middleware. Student documents, review data, `.env` and `.venv` are ignored by Git.
Do not put student details in source code or commit messages.

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
PDF text is supported, but PDF table, selection and signature checks stay manual.
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
- Require Area/Activity to identify a clear manufacturing process, test procedure,
  or named room/laboratory. Rules flag blank fields; AI assesses every nonblank
  entry by meaning, allowing equivalent terms and abbreviations without an approved
  list. Generic entries such as "in campus" should be flagged by AI. Without AI,
  the content assessment remains manual.
  No approved lab list is required.
- Compare the workspace with RA activities/equipment and ethics research activities.
  The separate activities–facilities check flags mismatches for manual review,
  distinguishes simulation-only projects from physical work, and requires evidence
  from both the location and activity descriptions before accepting an AI finding.
  It does not certify room suitability. Without AI it remains a manual check.
  Existing reviews gain this pending check without changing previous decisions or
  making API calls. Run pending AI checks to evaluate it on those submissions.
- Accept typed and image signatures; check presence only, never authenticity.
- Show available embedded images alongside supporting evidence and display each
  repeated source extract once. Images alone do not establish authenticity.
- Treat blank administrative answers or unchanged Y/N options as unanswered
  questions (Issue found), rather than ambiguity. An uninterpretable answer stays
  a manual check. Retained Y/N options with an answer entered in a reference field
  remain a completion concern; improve the student instructions rather than
  silently treating incorrect placement as correct completion.
- Flag missing fields, unchanged example rows and inappropriate entries.
- Require final risk scores to be strictly lower than the entered initial scores;
  equal/higher scores are flagged with the row and both values. This completion
  rule does not certify that the initial scores or controls are appropriate.
  Decimal Word list numbering is included when reading visible rating values.
- Flag non-H&S hazards for moderator review.
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
