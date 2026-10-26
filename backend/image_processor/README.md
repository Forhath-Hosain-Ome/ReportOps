# Image Processor Phase 1

Implementation base: `develop` at `c043345dfa7cdc1030cbd825ddcbf6beffdc4f96`.
This change is local implementation, not deployment authorization.

## Lifecycle and compatibility

Intake persists one `FolderReport` per directory directly containing accepted
images, including a separate `.` identity for loose images in a mixed upload.
`FolderImage` records retain relative source paths and original filenames.
Flat uploads retain the existing `style`/`uploaded` wrapper convention.
Nested reports exclude their descendants' images. Existing path, archive size,
expansion, collision and exclusive-write protections remain in force.

`process_folder_task` and `process_defect_docx_task` identify the same registered
task, `image_processor.process_defect_docx`. The positional arguments remain
compatible; new publications also carry a persisted generation and dispatch UUID.
Messages without durable identity are ignored rather than creating unaudited work.
Drain or explicitly reconcile legacy queued work before any future rollout.

Dispatch moves through REQUESTED, PUBLISHING, QUEUED, PROCESSING and TERMINAL.
Serialization failure is FAILED; transport failure after publication starts is
UNKNOWN. Neither FAILED nor UNKNOWN is worker-claimable. Publisher callbacks are
conditional and cannot overwrite an advanced dispatch. Retry creates a new
generation, including recovery from failed/uncertain publication without failed
report rows. An abandoned REQUESTED/PUBLISHING dispatch becomes recoverable after
its publication lease expires.

Workers, retry/recovery, artifact revocation and cleanup use the same PostgreSQL
session advisory lock per batch. Short row transactions fence writes by generation,
dispatch UUID, active run UUID and attempt/report identity. Reconnected sessions
cannot reuse lost execution ownership. This requires direct/session-affine
PostgreSQL connections; transaction-pooling proxies are not supported. SQLite
coordination exists only behind the explicit isolated-test setting.

Processing leases last 1,800 seconds, longer than the existing 1,500-second hard
worker deadline. Stale recovery also requires acquiring the batch lock. It covers
every unfinished intended REQUESTED/QUEUED/PROCESSING attempt, retaining valid
terminal results. Selective retry uses report IDs owned by the requested batch.

Successful outcomes, terminal attempt output and current report authority commit
atomically after DOCX validation. Files generated before a failed commit remain
uncommitted and cannot be downloaded. Historical attempts/outcomes are preserved.
Missing or invalid current artifacts revoke present authority without rewriting
terminal attempt history. Final reconciliation validates cardinality, accounting,
all intended terminal states and both newly generated and preserved artifacts.
Infrastructure failure never fabricates per-image FAILED outcomes.

Report COMPLETED means all accepted images succeeded with a valid DOCX; PARTIAL
requires both actual successful and failed images plus a valid DOCX. FAILED has no
current deliverable. A batch may be PARTIAL when some reports deliver and others
fail. Terminal progress is 100%; intermediate progress counts completed reports,
including partial/failed reports. REST and Image WebSocket snapshots share counters.

## API and settings

- `POST /image/folder/batches/<id>/retry/`: optional `report_ids` integer array.
  Missing/expired source returns HTTP 410 with `REUPLOAD_REQUIRED`.
- `GET /image/folder/batches/<id>/logs/`: paginated attempt history under
  `count`, `next`, `previous`, `results`, plus batch status/error metadata.
- Existing report DOCX URLs return raw DOCX with its MIME type and filename.
  The frontend service returns `{blob, filename, contentType}`; callers save once.
- Existing report PDF URLs convert on demand using a private LibreOffice profile,
  a 120-second timeout, checked exit status and structural PDF validation. The
  complete temporary tree is removed when the response closes, or immediately on
  conversion failure. Other modules' shared conversion helper is unchanged.
- `/ws/image/batches/<id>/progress/` authenticates and checks Image batch ownership;
  its `image_batch_<id>` group cannot collide with PUMA's `batch_<id>` group.
  PUMA no longer falls back to Image records, and checks its own batch owner.
- `GET/PATCH /image/settings/`: authenticated reads include `can_manage`.
  Only `is_superuser is True` may mutate settings. Retention is 1–720 hours;
  each dimension is 32–4096 pixels. Defaults are 24 hours and 325×265 pixels.
  New batches snapshot these settings and their expiry; changing settings does not
  rewrite existing jobs, attempts or output.

The default source root remains `/tmp/batch_uploads`; an explicit server-side
`IMAGE_PROCESSOR_STAGING_ROOT` may override it. Backend and worker must share that
root and MEDIA_ROOT, as in the current Compose mounts. Stored output paths are
strictly relative to MEDIA_ROOT. Output layout is
`<OUTPUT_DIR>/<batch>/<report>/<attempt UUID>/<filename>.docx`.

Retention cleanup selects database-owned expired batches. It claims maintenance
ownership before deletion, holds no row transaction during filesystem removal,
and checks exact source UUID/output batch identity and containment again immediately
before deletion. Empty paths, roots, siblings, traversal and symlink redirects are
rejected. Removed/absent/skipped/errors counts and deletion markers are truthful.
Historical dispatch UUIDs do not prevent terminal cleanup.

## Migration and deployment gates

The repository previously contained no Image Processor schema migrations.
`0001_initial` records the pre-existing model definitions; `0002_reliability` adds
the new state. `0003_report_identity` performs a duplicate preflight before adding
the report identity constraint. PostgreSQL locks writers across that preflight and
constraint creation. Duplicates abort the migration without rewriting rows.

Run this read-only command against the actual intended database before adoption:

```sh
python manage.py image_processor_preflight
```

It reports applied Image migrations, physical field types/defaults/nullability,
indexes/constraints and duplicate identity count. It never fakes or adopts a
migration. If tables already exist, compare their complete schema and migration
history with the baseline before designing a reviewed adoption/backfill procedure.
Do not blindly use `--fake-initial`, edit applied migrations or delete duplicates.
Legacy rows have no invented manifests, staging UUIDs or attempt authority: their
adoption and retained-artifact history require real data/schema inspection.

**Existing deployment schema/history/data adoption remains NOT VERIFIED.**
Fresh isolated PostgreSQL migrations and duplicate-preflight rollback are tested;
that does not establish compatibility with a pre-existing deployment database.

Image Processor now has defined migrations and does not need runtime generation.
The global entrypoint's existing `makemigrations` remains unchanged because other
out-of-scope apps still lack committed initial migrations. Removing that global
step requires their separate migration work. No Final Summary/extraction/export
implementation was modified by this change.

Rollback must preserve schema and audit evidence: stop workers/publication and
review the compatible code/data path. Do not reverse these migrations over real
attempt history or retained artifacts as an automatic rollback.

## Verification

Run from `backend` with the project dependencies:

```sh
python -B -m django test image_processor mail_download.tests --settings=image_processor.tests.settings
python -B -m django makemigrations image_processor --check --dry-run --settings=image_processor.tests.settings
python -B -m django check --settings=image_processor.tests.settings
```

The PostgreSQL variant uses `image_processor.tests.settings_postgres` and an
explicit disposable localhost database on port 55438. It never loads deployment
credentials. PUMA's migration under `tests/puma_migrations` is test-only, to verify
real numeric-ID collision and ownership without changing PUMA production migrations.

Verification on 2026-10-26:

| Check | Result |
| --- | --- |
| Windows + PostgreSQL 18 + Redis 7 affected backend suite | 111 tests passed, 1 platform skip |
| Windows + SQLite affected backend suite | 111 tests passed, 3 platform/PostgreSQL skips |
| Linux + SQLite affected backend suite | 111 tests passed, 5 platform/PostgreSQL skips |
| Redis/PostgreSQL focused integration suite | 6 passed, including real queued task consumption |
| Image migration drift | No changes detected |
| Isolated Django system checks | No issues |
| Fresh PostgreSQL migrations, physical metadata and duplicate preflight | Applied 0001–0003; 7 Image tables; zero duplicate identities |
| Duplicate migration refusal | Tested without rewriting rows |
| Frontend production build | Passed |
| Changed/new frontend lint comparison | No introduced errors across 16 files |
| Full frontend lint | 390 existing errors; remains a global check failure |
| Global migration drift | Existing Final Summary initial migration missing; outside this change |
| Scoped security heuristic scan | No findings; not a security guarantee |
| Real Linux LibreOffice conversion | Valid one-page PDF, 9,614 bytes; full temporary tree removed after response close |

Browser checks against disposable PostgreSQL/API data confirmed mixed loose/nested
intake, explicit unsupported-file feedback, genuine partial-image failure, retry
without reupload, displayed attempt/image failure history, exactly one DOCX download,
Image report navigation, settings editing and a new job using 80×60 pixels/two-hour
retention while the earlier job retained its 325×265/24-hour snapshot. An expired
access-token request successfully used `/auth/token/refresh/` and retried the Image
request. The Image service uses an origin-root client so auth refresh is not prefixed
with `/image/`; other modules' clients were not changed.
The development proxy reserves `/image/` for API paths so reloading the `/image`
screen reaches the frontend. Image lists trust the already owner-scoped API rather
than hiding records when the client profile has not hydrated after a reload.

The queued-worker test uses a real Celery worker. It defaults to an in-memory broker;
set `IMAGE_TEST_BROKER_URL` to an explicitly isolated broker to exercise Redis.
Transport uncertainty and interrupted publication are fault-injected regressions.
Real deployed broker/worker/shared mounts and the existing schema/adoption preflight
remain rollout checks. Browser UAT used eager task execution and REST polling;
Channels ownership, snapshots and namespace isolation were separately exercised
through real ASGI communicators.

Delivery gates: Requirement Freeze and Design were explicitly approved. Local
implementation, self-review, sibling review and scoped adversarial tests are
recorded above. Full regression is not globally PASS because of the existing lint
and other-app migration failures. No push, PR, merge or deployment is authorized or
performed. The scope spans more than the default review budget; split into reviewed
schema/lifecycle, API/integration and frontend delivery slices before any future PR.
