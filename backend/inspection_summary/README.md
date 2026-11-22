# Inspection Summary — Round 103 QC Dashboard O30

QC Dashboard O30 is the merged O30:X31 summary banner under "Final Team Findings
(on 100% Team basis)". It is not source/detail O30. Its supported metric is the
existing defect-equivalent quantity:

matched Final defects × (matched 100% inspected quantity / matched Final inspected quantity).

Exact, case-sensitive, trim-only style intersection remains the sole comparison
scope. Duplicate records contribute normally. The report-data comparison model
supplies both the existing T26:T29 values and the O30 formatted summary; no source
format or defect-column position enters this calculation. Existing Decimal
calculation/rounding is preserved. Numeric zero produces "0 Defect-Equivalent Pcs";
no exact matches, missing quantities or a zero Final denominator remain unavailable.
Missing Final or 100% authority still omits the entire dashboard.

The original reference banner also contained a static "12 Inspectors Work" claim.
That unsupported workforce conversion remains excluded. O30 now displays only
the source-backed defect-equivalent finding; no personnel aggregate is inferred.
The existing dynamic-cell allowlist already permits O30. Canonical assets, merges,
styles, neighboring metrics and the preview response contract are unchanged.

Regression coverage is in `tests/test_dashboard_o30.py`: a positive reproduction
failed on both formats before the fix; matched/nonzero, valid-zero, unavailable,
no-match, missing-source, neighboring cells and 28/35/37/42/60 schemas are covered.

---

# Inspection Summary — Round 100 Structured Monthly adapter

`structured_monthly_100` adds a separate recognizer for the supplied monthly
operational layout. It proves merged three-row business headers, a two-column
date presentation area before Style, explicit Person/Inspection/Defect/Passed/
Ratio fields, merged category bands, literal labels and integer numbering 1..N.
Item/Iteam aliases belong only to this adapter. Filename, organization, reporting
period and sheet name are not detection evidence. Only visible sheets participate;
multiple authoritative tables fail closed.

The adapter declares numbered blank defects as zero across the full discovered
schema. Each definition retains ordinal, source number, category, literal label,
source column and same-category occurrence. It reads actual dates from the source
date column rather than evaluating date-echo formulas. Only identified inspection
records are normalized; blank/date-only template rows, Weekly Subtotal, TOTAL and
the following Top-5/helper presentation are excluded as detail authority.

Quantity authority remains consistent with Raw: consumed formula quantities need
cached results. Every detail defect quantity must reconcile with the cached or
literal declared defect quantity; an observed pass quantity must also reconcile.
No pass/defect values are invented when caches are missing. Cached source TOTAL
values, including each defect field, independently verify normalized aggregates;
uncached presentation totals are ignored, never used to reconstruct records.
Source ratio and Top-5 presentation formulas are not business authority.

Existing date aggregation and ReportBlock construction are shared unchanged.
Analysis, Summary, exact-style QC Dashboard, dynamic detail, charts, printing and
preview continue through common consumers. Presentation-only unheaded gaps are
omitted from the output projection. No lifecycle, database, storage, security,
canonical asset, deployment, route or dependency changes are needed.

The preview exposes the internal format and per-field source number. React only
maps the identifier to "Structured Monthly"; no format selector or calculations.
Business fixtures stay outside Git. Set `INSPECTION_SUMMARY_MONTHLY_FILE` for the
supplied workbook test; synthetic merged-header variants cover 28/35/37/42/60,
duplicates, formulas/caches, row boundaries, totals, output and preview parity.

---

# Inspection Summary — Round 99 contract

This approved revision supersedes the mandatory inputs, fixed 35-field detail and
always-four-sheet statements in the historical handoffs below.

Upload at least one `.xlsx` using `inspection_summary` and/or `hundred_percent`.
The legacy `raw` alias remains accepted, but cannot accompany `hundred_percent`.
Duplicate or unknown fields are rejected. Omitted sources retain empty name/hash
and the canonical reserved path in the existing job row, so storage containment,
retention, leases, recovery and ownership use the unchanged lifecycle. No migration.

Structural recognition resolves required business headers and explicitly category-
banded defect columns. The Raw adapter recognizes compact single-category tables
or the approved legacy label profile; the Structured adapter recognizes other
supported multi-category operational tables. Filenames and sheet names never
select a format. Unknown, overlapping, missing or unclassified fields fail closed.
Numbered schemas require every integer 1..N in source order and define sparse
defect blanks as zero. Supported dense schemas without a number band require all
defect quantities. All rows reconcile defect quantities before normalization.

The in-memory ReportBlock adds format, explicit business-column mapping and
blank policy; each defect preserves source column, ordinal, category, label and
same-category occurrence. Repeated labels remain independent fields. Future
adapters must prove an explicit mapping and reuse shared validation and reporting.

Analysis and Summary always render actual recognized blocks. The 100% block and
detail sheet exist only with a 100% source. QC Dashboard exists only with actual
Final and 100% authorities, including a valid empty exact-match intersection.
Analysis uses inspected quantity; Summary uses defect quantity; MANPOWER remains
Analysis-only. Exact, case-sensitive, trim-only style matching and all Top 5 ties
remain unchanged. No React business rules.

The canonical detail stencil expands to N separate columns with dynamic category
bands, numbering, result positions, chart ranges, filters and print bounds.
The immutable canonical asset and dashboard/static presentation are preserved.
Verification checks the package and independently checks dynamic headers,
categories, source quantities, subtotals, totals, chart and print/filter extents.

Preview additionally exposes `available_sections`, `sources`, column kind/category/
ordinal/occurrence and reconciliation format/field/category counts. The owner-only,
read-only endpoint retains existing 200/404/409/410 behavior. React uses explicit
capabilities for navigation, optional uploads, backend ratios and dynamic tables
inside the shared DashboardLayout, including a 390px viewport.

Regression coverage: `tests/test_dynamic_contract.py`, existing parser/writer/
canonical/API/preview suites, real PostgreSQL/broker/restart gates and frontend
browser tests. External business workbooks remain outside the repository.

---

# Inspection Summary — Round 96 web preview

The workbook contract below remains frozen. The authenticated `/inspection-summary`
route now uses DashboardLayout once and offers Overview, QC Dashboard, Analysis,
Summary and 100% Detail before the existing Result.xlsx download.

`GET /inspection-summary/jobs/<uuid:pk>/preview/` is authenticated and owner-scoped,
with no staff bypass. It returns 409 before completion, 410 after expiry, and 404
for missing jobs or unavailable output/input authority. Successful responses use
`Cache-Control: private, no-store` and expose `job`, `overview`, `dashboard`,
`analysis`, `summary`, `detail` and `reconciliation`.

The read model reparses retained, SHA-256-verified inputs using existing parser and
report-data functions. It validates output availability but does not reconstruct
business data from generated Excel, regenerate output, dispatch tasks, write data,
or add persistence/migrations. Matching, five distinct ranks and ties, ratios,
manpower and Friday-closing detail subtotals reuse existing backend helpers.
Manpower values retain the parser's string/null representation. Unsupported ratio
reduction stays null; equivalent findings reuse the canonical dashboard adapter.

The browser only formats values. Preview loads once after completion, is hidden
for new uploads and expiry, and can fail independently of a valid workbook download.
All detail fields remain accessible through a focusable table scroll container.
Tests live in `tests/test_preview.py` and `frontend/tests/inspection-summary.test.js`.

---

# Inspection Summary — Round 89 local handoff (2026-11-12)

This section supersedes all historical output contracts below. Output is exactly
QC Dashboard, Analysis, Summary, 100%, all visible and in that order.

## Canonical presentation and dynamic boundary

The explicitly approved composite reference is Result_1.xlsx (first three sheets)
plus Result - Template.xlsx (100%). canonical.py builds a sanitized, self-contained
OOXML asset offline. The bundled canonical.xlsx/json records source checksums,
original dashboard presentation, dynamic-cell allowlist and drawing/image/chart
fingerprints. Runtime never reads the external reference folder. lxml is already
an installed dependency; no dependency or deployment changes are required.

Dashboard drawing XML and image bytes are preserved. Chart formatting is preserved;
only chart caches and explicitly allowlisted cell values change. The exact allowlist
is canonical.DASH_DYNAMIC and templates/canonical.json. All other dashboard values,
styles, geometry, conditional formatting, images and print properties are tested.

Analysis/Summary copy the original per-stage row styles, merge geometry and charts.
Source visible order and parser recognition remain authoritative. Absent blocks are
removed, recognized empty blocks remain, INLINE-SPL/INLINE are independent, and the
Raw block replaces a visible 100% or appends once. Named block anchors exist on both
sheets. Top five distinct positive quantity ranks and all tied labels are identical;
Analysis divides by inspected quantity, Summary by defect quantity. Counts use
Total: NN-Audit or NN-Style; day counts use unique source dates.

Only Analysis has the canonical Raw MANPOWER row. Per explicit user decision the
aggregate persons value remains blank. Date-linked source values remain distinct,
including 52 and 20 on 05 Oct in the real sample. Missing personnel stays missing.
Unsupported buyer/team leader/person-equivalence values are blank.

Dashboard uses only Final and Raw records in the trim-only, case-sensitive string
style intersection. No suffix removal, coercion or fuzzy matching. Duplicate
records contribute normally. Re-Final, Random and inline stages never contribute.
The supplied real files have no exact matches; comparison totals are therefore zero
and ratios unavailable. Full Raw totals remain on Analysis/Summary/100%.

100% preserves the canonical defect/quantity bands, colors, 1..35 numbering and
charts. It retains all 83 source records and all 54 recognized fields. Necessary
adaptations replace calendar helpers with actual Date/Factory/Style, expose B/C,
append additional metadata, use actual date formatting, regenerate Friday-closing
weekly subtotals/grand total, freeze E4, and filter the operational table. Added
fields require fit-to-page printing; charts move below the table with fresh caches
and a source-neutral title. The original unused broken Summary chart is removed.
No historical worksheets, business cell values or chart caches are copied forward.

Verification compares the complete expected package, then checks the four-sheet
contract, duplicate coordinates, formula/error absence and Raw reconciliation.
Independent tests additionally compare original presentation fingerprints and
source-derived values so the verifier is not the only oracle.

## Evidence and current gate status

Evidence is external to Git under inspection-summary-round89 in this chat's
visualization directory: Result.xlsx, eight native Excel reference/output PDFs,
canonical-inventory.json, source/reference hashes and test logs.

Real reference: inspected 156132; pass 139557; defects/category sum 16575;
83 records; 13 dates; 12 styles; dashboard matched styles [].

PostgreSQL 13/13 and standalone real prefork SIGKILL/restart pass. Broker assertions
pass but its runner retains one PostgreSQL connection at database teardown, causing
an OperationalError. This is a failed clean-exit gate, not a green runtime result.
No protected services/tasks/storage/OPC/security code was changed to mask it.

| Round 89 gate | Result |
|---|---|
| Feature/security/OPC/real-reference suite | 148 total; 130 passed, 18 runtime skips |
| PostgreSQL concurrency/lifecycle | 13/13 passed, clean teardown |
| Real broker + prefork restart | Assertions pass; retained-connection teardown failure recorded |
| Standalone SIGKILL/restart | 1/1 passed, clean teardown |
| Sibling regressions | 133 total; 128 passed, 5 existing skips |
| Migration drift / Django check | No changes / no issues |
| Frontend build / feature lint | Passed / passed |
| Browser suite including mobile R78-01 | 4/4 passed |
| Full source lint vs base | 17 vs 17; shared generated cache 373; full 390 vs 390 |
| Native Excel prints | Dashboard 1, Analysis 1, Summary 1, detail 2 pages |
| Protected source and original workbook hashes | Unchanged |

The 54-column operational sheet is dense when printed to the original landscape
paper size; Excel retains every source value for inspection at normal zoom.
External deployment migration adoption remains unverified; no deployment attempted.

All prior sections below are historical evidence, not the current output design.

---

# Inspection Summary Phase 1 — Round 85 local AUDIT handoff

## Round 85 current output contract, 2026-11-12

The output contract in this section supersedes the historical single-Summary
workbook descriptions below. Exactly two visible worksheets are generated, in order:
`Summary`, `100%`. No historical/template sheets are copied.

The user confirmed `Result_1.xlsx` as the Summary visual reference and the six visible
inspection tabs in `Result - Template.xlsx` as Input A for reference acceptance.
The latter's 100% sheet supplies a layout reference only. All generated 100% numbers
and detail rows come exclusively from Raw.xlsx. Input files remain external and
unchanged. Tests accept an explicit INSPECTION_SUMMARY_SOURCE_FILE path, alongside
INSPECTION_SUMMARY_REFERENCE_DIR; they never infer Input A from a design filename.

### Renderer and data boundary

Summary uses the reference's A:M width, green merged block titles, compact metadata,
yellow Top 5 headings, borders, Calibri typography and landscape presentation.
render_summary_block returns the next available row; each actual block is followed
by one small spacer. Visible source order, absent types, recognized empty sections,
unknown-structure failure and INLINE/INLINE-SPL independence remain parser-owned.
One Raw summary replaces a visible 100% position or appends last. No six-block or
fixed-stage row map exists. Days and audit counts are distinct metrics.

The normalized ReportBlock exposes complete already-computed defect totals, unique
day count, Raw pass aggregate, styles, headers and source-backed detail rows. Existing
top_defects and extraction calculations retain their previous semantics. Additional
Raw prefix fields are read through the same cached-formula/error boundary because
they are now consumed by the output. No new source-recognition or sparse-schema rule
is introduced. Missing optional values remain missing; only approved sparse defect
blanks become zero. Optional text/nonnumeric quantities are preserved and do not
become invented numeric subtotals.

Top 5 presentation selects five DISTINCT positive quantities from complete category
totals. All ties retain their category/label identity and schema order. Ties are
bounded into chunks of up to three labels per rendered row, repeating the same rank,
quantity and ratio. Rank ratio = quantity / block defect total. Overall defect ratio
remains defects / inspected. No old template audit count, personnel name or buyer is
copied; personnel has the truthful Personnel / Inspector(s) label.

### Raw detail and verification

100% preserves recognized Raw header order and all prefix fields plus exactly 35
defect columns. Actual records are stably ordered by Inspection Date. Source Pass Qty
is copied and aggregated, never inferred. Category bands, numbered defect headers,
Friday-closing weekly subtotals and a grand total reflect the sample's useful
structure. Only actual records appear: no calendar placeholders or historical rows.
Nonadditive working-hour/inspector fields are not summed. Totals/subtotals are separate
from detail records; identify actual records by the Inspection Date value.

Freeze C5, filter, repeated headers/date column and printed row numbers support wide
table use. Horizontal panel boundaries split category captions safely. The table uses
A4 landscape at 75% across multiple pages, independently of Summary's fit-to-width
layout. Native Excel on this workstation cannot assign A3 paper; the final workbook
therefore explicitly uses the verified A4 setting.

verify_report checks output security ceilings before reopening, exactly two visible
sheets, dynamic anchors and positioning, every expected Summary value, exactly one
Raw summary, exact detail headers and values, record/day counts, inspected/pass/defect/
category reconciliation, duplicate names within their Excel scope, valid print areas,
extra Summary content, formulas and errors. Sheet-local print-area names are valid
distinct scoped names. Unexpected invariant failures still propagate through the
unchanged worker failure boundary.

### Visual/reference acceptance and material differences

Reference acceptance: Final, Re-Final, Random, INLINE-SPL, INLINE, 100%; inspected
156132, pass 139557, defects 16575, 35-category sum 16575, 83 detail records, 13 days,
12 unique styles. Final has four inspection days and six audits, not stale template
counts. Top-ranked Final defect ratio is 7/36 = 19.44%.

Fresh output and native print evidence are outside Git under inspection-summary-round85
in the chat's visualization directory. All three Summary pages and all twenty detail
pages were rendered and inspected. Detail consists of five horizontal panels over
four row sections; headers and record references repeat. No blank print pages or
overlapping blocks were observed.

Material differences from Result_1: six actual blocks instead of its five rendered
reference blocks; current source-backed dates/counts; no unsupported Buyer/Team Leader
values; no copied pie charts or stale chart data. Summary prints over three readable
pages instead of compressing the reference to one page. Detail preserves all 83 Raw
records/54 columns instead of the sample's daily/calendar projection and side panels.
These differences follow the Round 85 data contract rather than copying stale cells.

### Mobile and audit scope

R78-01 uses component-local fieldset minInlineSize:0, full width and border-box sizing,
plus constrained full-width file inputs. The original overflow assertion remains.
Browser tests add long filenames, loaded fonts and completed/download-state checks.
The measured viewport and document width are both 390px after selection and settling.

No models, migrations, services, tasks, storage, security/OPC code, settings, deployment
configuration or protected sibling implementation changed. The prior migration-adoption
precondition and hourly execution-recovery tradeoff remain. No commit, push, PR, merge
or deployment is authorized/performed. Independent AUDIT is next. Open questions: none.

Historical Round 71–78 evidence follows; its one-sheet contract is superseded above.

### Round 85 final quality evidence

| Check | Result |
|---|---|
| Feature Django suite with external Input A/Raw acceptance | 138 total; 120 passed, 18 runtime skips; 67.964 s |
| Disposable PostgreSQL suite, separate invocation | 13/13 passed; 5.121 s; fresh migration applied; clean exit |
| Real Redis/Celery plus prefork SIGKILL/restart, separate invocation | 5/5 passed; 15.197 s; clean exit |
| Migration drift / Django check | No changes detected / no issues |
| Image Processor and Mail sibling suite | 128 passed, 5 existing skips; 31.969 s |
| Frontend production build / feature lint | PASS; 190 modules / PASS |
| Browser suite | 4/4 passed; 16.074 s; long filenames, loaded fonts, 390px and terminal states |
| Full lint comparison | Base/current 390/390 using equivalent cache; source-only 17/17; introduced 0 |
| AST / diff checks / protected source and input hashes | PASS |

All 18 feature-suite runtime skips executed in the separate PostgreSQL/broker suites.
An exploratory combined 18-case invocation passed its assertions but exited nonzero
during test-DB destruction because one connection remained open. This reproduced in
the combined runner. The documented separate 13-case and 5-case commands both passed
with clean teardown on final source. No dispatch/storage/worker implementation was
changed to hide that test-runner limitation. The full diagnostic log remains outside
Git as runtime-final.log; separate clean logs are postgresql-final.log/broker-final.log.

| Delivery gate | State | Evidence |
|---|---|---|
| Requirement Freeze / Design | PASS | Round 85 plus confirmed reference/Input A roles |
| Implement | PASS | Twelve scoped files; two-sheet rendering and mobile fix |
| Self-review | PASS | Complete Round 78-to-85 diff; data, ranking, verification and layout review |
| Sibling Harvest | PASS | Existing consumers updated only for output contract; sibling code unchanged |
| Adversarial Tests | PASS | Dynamic subsets, ties, missing/text metadata, output tampering and existing security cases |
| Full Regression | PASS | Named separate required suites/checks above; combined-run limitation disclosed |
| PR | NOT STARTED | No commit/push/PR/merge/deployment authorization |

Base: `e525aec5238b0dea7fe352bf175624d8b096ae5c` (`codex/deployment-readiness`).
Feature branch: `codex/inspection-summary-phase1`. Changes are local and uncommitted.
No push, PR, merge, deployment, database adoption, or production migration was performed.

## Contract and ownership

Two authenticated XLSX uploads create an owner-only UUID job. Default Celery queue;
existing shared MEDIA_ROOT. One indivisible Result.xlsx, exactly one Summary sheet,
vertical blocks in visible source order. Hidden/very-hidden ignored. Unknown visible
structures fail the whole job; recognized empty sheets retain an empty-state block.
100% is rebuilt only from Raw, replaces its visible position or appends last once.
Existing Final Summary, Image Processor, PUMA, Top Five and Mail Download code stays unchanged.

Missing quantities stay missing. Required formula caches must be available; no Excel
formula engine is invoked. The user explicitly confirmed an exception after inspection:
blank Raw defect cells mean zero ONLY for the recognized sparse schema with exactly
35 unique defect labels and an immediately preceding ordered numbering band 1..35.
All other missing values remain missing. Pass quantity is never inferred.
Ordinary sheet defects have independent schemas; top-five values report recorded counts.
Personnel is included only when source values exist; no inferred personnel calculation.

Storage keys use server UUIDs and MEDIA_ROOT-relative paths. Inputs are hashed and
revalidated in the worker. Temporary output is verified/reopened before os.replace;
a locked status/run-token check controls final authority. Upload dispatch occurs after
commit; uncertain broker outcomes remain PENDING/UNKNOWN and are recoverable. A stale worker cannot
publish or overwrite a newer state. Fixed expiry is 24 hours from intake; download
checks expiry immediately and returns 410 even before cleanup. Cleanup is hourly at
minute 15, preserves audit rows, and protects PROCESSING jobs with live execution leases. Maintenance ownership
and a process lock fence deletion of the exact job directory. Long tasks have
1200/1500-second limits and a separate 1800-second execution lease. Execution recovery,
then dispatch recovery, run before hourly cleanup. Expired execution authority is
revoked before reprocessing or retention deletion (Round 77 below).

## Round 77 current handoff — ready for independent AUDIT, 2026-11-05

Only R76-01 through R76-05 changed. Earlier sections below are historical evidence;
their statements that runtime gates are blocked or abandoned PROCESSING is retained
are superseded by this section. No commit, push, PR, merge or deployment occurred.

### Execution recovery / R76-01

The model and still-unreleased initial migration add only
`processing_lease_expires_at` (nullable, indexed). Claim sets the lease to 1800 seconds,
separate from the 120-second publication lease and beyond the 1500-second hard limit.
Progress updates and final publication require the current run, dispatch generation,
token, valid execution lease, valid retention and no maintenance owner. Publication
rechecks under the row lock before atomic replacement of the sole Result.xlsx.

Recovery row-locks an expired PROCESSING job, revokes the old run and clears output
authority. Legacy NULL leases use started_at/created_at plus 1800 seconds. An expired
job becomes terminal JOB_EXPIRED and may enter fenced cleanup. An unexpired job gets
a fresh dispatch generation/token and REQUESTED publication intent. After commit,
retained input hashes and workbook security are revalidated before durable publication.
Unavailable/invalid sources terminalize safely; unexpected infrastructure failures
remain observable. No row lock spans validation or broker I/O. A recovery crash is
bounded by the existing publication lease. Old workers/deliveries cannot regain
authority; live execution leases remain protected from cleanup.

The existing hourly maintenance task performs execution recovery, publication recovery
and cleanup. Automatic detection may wait until the next hourly tick after lease
expiry. Recovery does not depend on Celery redelivery. No new queue, schedule, storage
backend or deployment setting is introduced; backend/worker still share MEDIA_ROOT.

Migration assumption: initial 0001 has not been adopted outside disposable test DBs.
The feature remains untracked/uncommitted at base e525aec and no shared migration or
deployment was performed here. External adoption is unverified; if adoption occurred,
a forward migration is required before delivery. Swappable auth dependency and all
sibling migrations are unchanged. Fresh disposable PostgreSQL migration passed.

### OPC/package security / R76-02 and malformed inputs / R76-04

New opc.py resolves effective content types, package officeDocument authority, actual
workbook relationships, sheet identities and shared-string authority. Targets resolve
relative to their source part with bounded root navigation; missing, external authority,
unsupported, ambiguous or escaping targets fail before openpyxl. Duplicate logical
sheets targeting one normalized physical part are rejected. Shared-string authorities
must agree and be unique. Relationship roles must match content types. Relocated parts,
including non-.xml names, receive their semantic worksheet/shared-string budgets.
All typed worksheet parts are charged, even unreferenced ones. XML remains streamed
once per part without trees; metadata retention is capped at 10,000 entries. All prior
resource ceilings below are unchanged. Percent-encoded package URIs and noncanonical
manifest overrides are explicitly unsupported to avoid reader-normalization differences.

Known malformed compression/package/XML errors include zlib.error, BadZipFile,
LargeZipFile, struct.error, EOFError and XML/Unicode errors. They become safe structured
INVALID_WORKBOOK HTTP 400 responses. PermissionError, filesystem OSError, database and
programming/invariant failures are not broadly converted to user-input errors; existing
fenced failure persistence and original-exception propagation remain in force.

### Sparse schema / R76-03 and print continuation / R76-05

Only genuine integer markers 1..35 authorize sparse blank-defect zero filling.
Boolean, string, partial, duplicate, out-of-order and nonintegral marker bands fail
RAW_DEFECT_SCHEMA_INVALID. An entirely absent band remains dense and requires all
defect values. All other missing-value, pass and personnel rules remain unchanged.

Daily rows are divided into segments of at most 20, each starting at an explicit
print-page boundary with block identity and the actual column headings. These context
rows do not create extra business blocks or change calculations. A 45-day regression
checks three segments and preservation of every date/value. Fresh real output was
exported read-only through native Excel: all seven rendered pages were inspected.
Page seven has the 100% daily context, four headings and all 13 dates; no clipping,
overlap, blank page or page-count regression from Round 76 was observed.

### Current verification

| Command / gate | Result |
|---|---|
| python -B -m django test inspection_summary --settings=inspection_summary.tests.settings | 132 tests: 114 passed, 18 opt-in runtime skips; 35.921 s |
| test_postgresql with settings_postgresql and disposable opt-in | 13/13 passed; 2.490 s; fresh PostgreSQL migrations applied |
| test_broker_integration + test_worker_restart with real broker opt-in | 5/5 passed; 12.835 s; real Redis/Celery, no eager substitution |
| makemigrations inspection_summary --check --dry-run with test settings | No changes detected |
| django check with test settings | No issues |
| image_processor mail_download.tests with sibling test settings | 133 tests: 128 passed, 5 existing skips; 33.034 s |
| npm run build | PASS; 190 modules |
| Feature ESLint | PASS |
| Full ESLint comparison | Base 390 errors; feature 390; introduced 0; baseline still fails |
| node --test tests/inspection-summary.test.js | 4 passed; 0 skipped; 15.879 s |
| AST parse, git diff --check, protected paths and prior evidence hashes | PASS |

All 18 tests skipped in the SQLite run executed successfully against disposable
PostgreSQL/Redis in isolated Docker containers with no host port exposure and a
read-only source mount. Only task-owned containers and temporary state were used.
PostgreSQL tests include recovery claim races, old finalization/progress fencing,
cleanup after revocation and terminal non-regression, alongside all prior eight cases.
Broker tests retain all four previous cases, including uncertainty and unexpected
failure. The fifth starts a real prefork worker subprocess, uploads a job, waits for
PROCESSING and temporary output, SIGKILLs its process group (exit -9), verifies persisted
abandonment/live-lease protection, safely simulates expiry, starts a replacement worker,
recovers with fresh authority, rejects old run/delivery, downloads valid Result.xlsx
and verifies eventual retention cleanup/410. Injected exceptions do not substitute
for worker death. Run test_worker_restart on POSIX with explicit disposable opt-ins;
settings_worker additionally constrains the database and owned temporary MEDIA_ROOT.

Real business regression: Inspection Qty 156132; Defect Qty 16575; 35-category sum
16575; 83 detail records; 13 Inspection Date days. Output has exactly Summary and
six block anchors: Final, Re-Final, Random, INLINE-SPL, INLINE, 100%. Exactly one
100% block, no Excel error/formula literals; output reopens and verifies. Source files
remain external and unchanged. Fresh Result.xlsx, native PDF, seven page PNGs and
the complete Round 76-to-77 diff are outside Git in inspection-summary-round77 under
the chat's visualization directory.

Self-review covered the full remediation diff, stale execution/publication/cleanup
races, OPC normalization/aliases, strict marker types, narrow exception conversion,
unchanged calculations and migration correspondence. No protected sibling, frontend,
configuration or Round 73 evidence bytes changed in this round. Independent AUDIT is
still required; no release approval is claimed. Open questions: none.

Exact Round 77 files, relative to backend/inspection_summary/:

```text
README.md
migrations/0001_initial.py
models.py
opc.py
raw_parser.py
services.py
tasks.py
tests/package_fixtures.py
tests/settings_worker.py
tests/test_execution_recovery.py
tests/test_opc.py
tests/test_postgresql.py
tests/test_raw_parser.py
tests/test_security.py
tests/test_worker_restart.py
tests/test_writer.py
tests/worker_runtime.py
workbook_security.py
writer.py
```

## Round 71 historical local verification on 2026-11-01

- 50 feature Django tests passed, no skips, using isolated in-memory SQLite settings.
- This includes actual business files through authenticated upload, parsing, rendering,
  verification and authenticated streamed download. Real workbooks were never committed.
- Raw verified: Inspection Qty 156132; Defect Qty 16575; all 35 category totals 16575;
  83 detail rows aggregated into 13 inspection days. Totals/footer row excluded.
- Visible output blocks: Final, Re-Final, Random, INLINE-SPL, INLINE, 100%.
  Their defect schema sizes: 78, 78, 78, 78, 35, 35.
- Existing Image Processor/Mail test selection: 133 tests; 128 passed, 5 existing
  platform/PostgreSQL skips. Existing modules and migrations are unchanged.
- Four Node/Playwright browser tests passed: auth, two inputs/poll-stop/download,
  structured failures, expired blob error. Mobile 390px overflow assertion included.
- New frontend source and tests: ESLint passed. Production Vite build passed.
- Full frontend lint comparison: current 390 errors, clean base 390, introduced 0.
  The full lint gate remains failing; no claim of a globally green repository.
- Feature-only migration drift: no changes detected. Isolated Django check: no issues.
- Proxy API/page separation and protected-path Git diff checks passed.

Commands from backend, with repository-constrained dependencies in a temporary test environment:

```text
python -B -m django test inspection_summary --settings=inspection_summary.tests.settings
python -B -m django makemigrations inspection_summary --check --dry-run --settings=inspection_summary.tests.settings
python -B -m django check --settings=inspection_summary.tests.settings
python -B -m django test image_processor mail_download.tests --settings=image_processor.tests.settings
```

Set INSPECTION_SUMMARY_REFERENCE_DIR to a local directory containing the supplied
Inspection Summary, Raw.xlsx and Result.xlsx for real-file acceptance. The tests skip
those acceptance cases when the directory is absent; synthetic tests still run.
They never load deployment settings or secrets. No real business data belongs in Git.

Frontend browser tests use an explicitly localhost Vite server at port 5187 and
externally supplied Playwright through NODE_PATH, following existing test conventions:

```text
node --test tests/inspection-summary.test.js
```

## Round 71 historical verification limits (superseded by Round 75 below)

The next required round is AUDIT. No independent AUDIT is claimed by implementation.
PostgreSQL concurrent claims/cleanup and real broker/worker deployment integration have
not been exercised for this feature. Browser tests intercept feature APIs; actual-file
backend acceptance is a separate real parser/API test, not a deployed browser UAT.
Nginx templates were checked structurally; no live Nginx/deployment was changed.
Full frontend lint remains blocked by the unchanged 390-error baseline.
The diff exceeds the default 20-file/800-line delivery review budget; audit and slice
before any subsequently authorized push/PR. No existing migration was edited.

| Gate | State | Evidence |
|---|---|---|
| Requirement Freeze | PASS | Round 71 plus explicit sparse-Raw clarification |
| Design | PASS | Approved Round 71 draft on e525aec |
| Implement | PASS | Local app/API/writer/UI/proxy integration, one new migration |
| Self-review | PASS | Complete source/diff review and focused corrections |
| Sibling Harvest | PASS | Existing pipelines untouched; 128 sibling tests passed |
| Adversarial Tests | BLOCKED | Local cases pass; PostgreSQL concurrency not exercised |
| Full Regression | BLOCKED | Global lint baseline; runtime integration not verified |
| PR | NOT STARTED | No push/PR authorization or action |


## Round 75 remediation — independent audit next; delivery BLOCKED

Only R74-01 through R74-04 are remediated. All business rules, frontend/config,
protected sibling paths, and Round 73 evidence artifacts remain unchanged. The
frozen findings and required design are embedded in the user's Round 75 request;
no separate Round 74 audit document was supplied in this checkout.

### Durable dispatch (R74-01)

Business status stays PENDING/PROCESSING/COMPLETED/FAILED. Seven model additions:
`dispatch_generation`, `dispatch_token`, `dispatch_state`,
`publication_lease_expires_at`, `last_error_code`, `maintenance_token`,
`maintenance_started_at`. Only the feature's unreleased 0001_initial is updated;
its swappable auth dependency is retained. No sibling migration is changed.
Assumption: the feature initial migration has never been adopted outside disposable
test databases. Evidence available here: feature source/migration remain untracked,
HEAD equals base, and this chat has performed no deployment or non-test migration.
External database adoption cannot be independently established from this checkout;
if it occurred, this assumption must be revisited before migration delivery.

Intake commits REQUESTED intent with generation=1, UUID token, 120-second publication
lease. Publisher row-locks and claims PUBLISHING, commits, preflights JSON serialization,
then sends on the default celery queue outside a DB transaction. Serialization failure
proving no I/O sets TERMINAL/FAILED. Transport uncertainty sets UNKNOWN, not business
FAILED. Publisher results are conditional on generation/token/PUBLISHING/PENDING and
cannot regress PROCESSING or TERMINAL. Only matching PUBLISHING/QUEUED deliveries may
claim a run UUID. An expired REQUESTED/PUBLISHING/UNKNOWN lease is recovered internally
with a fresh generation/token and post-commit publication. Old deliveries/callbacks
cannot acquire authority. The existing hourly cleanup task invokes recovery first;
recovery scheduling latency can therefore reach approximately one hour, while the
publication lease itself is 120 seconds. There is no new queue or manual retry UI.

### Maintenance ownership (R74-02)

A row-locked claim rechecks expiry, status, run/dispatch ownership, existing maintenance
lease and server-derived path identities. PROCESSING is always skipped, even if old
or expired. Fresh ownership is persisted before filesystem I/O. The maintenance lease
is 300 seconds; a stale claim is reclaimable. A nonblocking OS lock spans claim,
delete and conditional marker finalization outside the DB transaction. It prevents
a paused old deleter from racing a new claimant after lease expiry; process death
releases it. Destruction re-resolves the exact UUID namespace. Marker updates require
the same maintenance token; successful finalization clears ownership. Exceptions keep
truthful markers and are raised for task failure; leases permit later recovery.
Missing directories finalize normally, repeated cleanup is idempotent.

The empty lock inode is outside the deleted job tree and intentionally never
unlinked (unlink could split ownership across two inodes). It remains alongside the
audit row, contains no business data, and requires shared-filesystem advisory-lock
support. Tests exercise Windows locking locally; Linux/PostgreSQL deployment runtime
has not been exercised. All PROCESSING rows are conservatively retained; this change
does not add crash recovery for abandoned execution runs.

### Streaming workbook security (R74-03)

ZIP members stream once per validation through XMLParser event callbacks using a
custom target that constructs no Element/tree. No fromstring, full-member buffering,
or second content-types parse remains. XML bytes are fed in 16 KiB chunks; DTDs are
rejected by parser callback. External metadata allowlist/keep_links=False remain.
Parser entry preflight and dimension checks guard direct parser calls too.

Security/resource ceilings (not business schema limits):

| Ceiling | Limit |
|---|---:|
| Input XLSX bytes | 50 MiB |
| Expanded workbook bytes | 200 MiB |
| ZIP entries / directory bytes | 10,000 / 4 MiB |
| Compression ratio | 100 |
| XML bytes per member | 32 MiB |
| XML elements per member / entire workbook | 1,000,000 / 3,000,000 |
| XML nesting / attributes per element | 64 / 64 |
| Worksheet parts / workbook sheet identities | 128 / 128 |
| Rows / columns per sheet | 200,000 / 512 |
| Cells per sheet / workbook | 500,000 / 2,000,000 |
| Sheet extent / aggregate sheet extents | 2,000,000 / 2,000,000 |
| Shared strings | 200,000 |
| Individual text/rich string/attribute value length | 32,767 characters |
| Aggregate character data | 16,000,000 characters |
| Merged ranges per sheet | 10,000 |

Measured with tracemalloc enabled (validator only; input bytes prebuilt; not process RSS):
Inspection Summary accepted in 6.151 s, peak 434,176 bytes; Raw accepted in 0.457 s,
peak 217,365 bytes. An uncompressed ZIP member with 1,000,001 tiny elements rejected
at the element ceiling in 7.920 s, peak 142,092 bytes. These are local observations,
not production performance guarantees. Adversarial tests also cover depth, worksheets,
rows, columns, cells, shared strings, rich/individual strings, dimensions, merges,
aggregate elements/text, DTD and external relationships.

### Exception contract (R74-04)

Known WorkbookValidationError: persist structured FAILED under current run authority,
return a business result. StaleRun: ignore without authority changes. Unexpected
RuntimeError/OSError/invariant/unclassified error: attempt fenced durable FAILED,
log safe code/type, then re-raise original so Celery marks FAILURE. If failure
persistence itself fails, the original unexpected exception is preserved. Output
verification invariant errors are unexpected OutputVerificationError, not user input
errors. Temporary cleanup errors are observable and cannot mask an already propagating
execution error. API errors never include internal exception messages or storage paths.

### Current verification

Feature, migration drift, Django checks, sibling tests, frontend build/feature lint,
full lint comparison, browser tests and real-file generation were executed locally.
Final counts and commands are recorded in the Round 75 chat report. No eager mode is
used to claim broker integration. Eight PostgreSQL-specific concurrency tests and four
real Redis/Celery tests are opt-in and remain BLOCKED here. Docker Linux engine is
unavailable (dockerDesktopLinuxEngine pipe absent), no localhost service responded on
PG 55475 or Redis 56375, and the temporary Python environment lacks psycopg/psycopg2.
No production credential/configuration was used and no Docker engine was started.

Concurrency suite: independent thread connections with TransactionTestCase cover
single run claim, old-generation rejection, maintenance claim race, full cleanup race,
cleanup during active writer, terminal non-regression, stale publication, duplicate
completed delivery. Broker suite uses a real Celery solo worker thread, Redis DBs
14/15, PostgreSQL and shared MEDIA_ROOT for upload/commit/download, duplicate delivery,
accepted-then-exception recovery, unexpected worker failure and missing input. Worker
restart/redelivery is not covered. These suites are source only until real services run.

Disposable-only commands (explicit opt-in, localhost fixed ports; never deployment settings):

```text
INSPECTION_SUMMARY_DISPOSABLE_POSTGRES=1
python -B -m django test inspection_summary.tests.test_postgresql --settings=inspection_summary.tests.settings_postgresql --noinput
INSPECTION_SUMMARY_REAL_BROKER=1
python -B -m django test inspection_summary.tests.test_broker_integration --settings=inspection_summary.tests.settings_postgresql --noinput
```

The public disposable PostgreSQL credentials in test settings are fixture values only;
server/database names are constrained to this test setup. A repository-pinned psycopg2
installation in the temporary test environment is also needed before those runs.

Self-review checked the entire Round 73→75 remediation diff, generation/result CAS,
run/maintenance authority, lease recovery, advisory-lock inode lifetime, exception
preservation, streaming counters and migration correspondence. No protected sibling,
frontend/config or audit evidence changes were found. No commit/push/PR/merge/deploy.
Open questions: none. Release/runtime gates remain BLOCKED pending disposable
PostgreSQL and Redis/Celery execution and independent AUDIT.


### Round 75 final execution evidence

All Python commands below used the existing temporary, repository-constrained Python
installation, from backend, with INSPECTION_SUMMARY_REFERENCE_DIR pointing to the
user's external Referance directory. Only disposable test databases/files were used.

| Command / check | Result |
|---|---|
| python -B -m django test inspection_summary --settings=inspection_summary.tests.settings | 94 tests: 82 passed, 12 skipped (8 PostgreSQL + 4 broker), 21.895 s |
| python -B -m django makemigrations inspection_summary --check --dry-run --settings=inspection_summary.tests.settings | No changes detected |
| python -B -m django check --settings=inspection_summary.tests.settings | No issues |
| python -B -m django test inspection_summary.tests.test_postgresql --settings=inspection_summary.tests.settings_postgresql --noinput (disposable opt-in) | BLOCKED: missing psycopg/psycopg2; Docker engine unavailable; disposable port unavailable |
| Real Redis/Celery suite | BLOCKED: no disposable broker/PostgreSQL; 4 tests not executed, no eager substitute |
| python -B -m django test image_processor mail_download.tests --settings=image_processor.tests.settings | 133 tests: 128 passed, 5 existing skips, 33.785 s |
| npm run build | PASS; 190 modules |
| ESLint feature page/form/client/browser test | PASS |
| Full ESLint feature vs clean base | 390 errors vs 390; introduced 0 (full lint remains failing) |
| node --test tests/inspection-summary.test.js | 4 passed, 0 skipped, 13.968 s |
| AST parse; protected-path diff; frontend/config byte comparison to Round 73 | PASS |
| Round 73 evidence artifact hashes | Unchanged |

Fresh review workbook is outside Git in the chat's visualization directory under
inspection-summary-round75/Result.xlsx. It reopens with exactly Summary, six block
anchors in Final, Re-Final, Random, INLINE-SPL, INLINE, 100% order; verify_report finds
exactly one 100% and no formula/error literals. Real acceptance: inspection 156132,
defects 16575, 35-category sum 16575, 83 detail records, 13 days. Existing tests retain
missing-value, sparse-schema, pass/personnel, visibility, empty/unknown sheet, owner
and expiry assertions. No user workbook was modified or added to Git.

Exact remediation files (relative to repository root; all inside feature app):

```text
backend/inspection_summary/README.md
backend/inspection_summary/migrations/0001_initial.py
backend/inspection_summary/models.py
backend/inspection_summary/parser.py
backend/inspection_summary/services.py
backend/inspection_summary/storage.py
backend/inspection_summary/tasks.py
backend/inspection_summary/tests/helpers.py
backend/inspection_summary/tests/settings_postgresql.py
backend/inspection_summary/tests/test_api.py
backend/inspection_summary/tests/test_broker_integration.py
backend/inspection_summary/tests/test_lifecycle.py
backend/inspection_summary/tests/test_postgresql.py
backend/inspection_summary/tests/test_raw_parser.py
backend/inspection_summary/tests/test_security.py
backend/inspection_summary/tests/test_writer.py
backend/inspection_summary/views.py
backend/inspection_summary/workbook_security.py
backend/inspection_summary/writer.py
```
