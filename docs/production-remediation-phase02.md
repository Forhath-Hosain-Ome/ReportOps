# Phase 02 — Image Processor multi-folder and secure ZIP backend

## Requirement freeze and base safety

One review question: do folder uploads and one ZIP archive feed the same contained batch contract?
Current remote develop/base: `4575ef744e32ec1f78fb7112fa0e77fc507ffa4a`. Both this merge and approved Phase 01 head `f95706b5da469862c7bf24cd6f7da77178ffe6b2` are verified ancestors. Branch: `feat/image-processor-multi-folder-zip-backend`, created from current origin/develop in an isolated worktree.
Original repository: `D:/Project/UQ_GU_Web_Summary`; remote: `https://github.com/Forhath-Hosain-Ome/UQ_GU_Web_Summary.git`. Original local develop remains at `3fb8aa8` with its existing changes preserved. Staged: extractor analyses/scripts/test and final_summary fields initializer. Unstaged: Dockerfiles, entrypoint, settings, Compose. Untracked: local skills, architecture/context documents, environment example and rotated logs. None are included.

User authorized inspection, characterization, contract freeze, minimal implementation, tests, commit and PR; no merge/deployment. No frontend, schema, dependencies, worker rewrite, staging-parent permissions or later-phase repairs.

## Existing behavior characterization before ZIP implementation

The existing API stores multiple top-level/nested folders in a UUID job; total_folders counts top-level directories, owner is request.user, and Celery receives that root once. Phase 01 tests cover single/multiple/nested folders and identical filenames in distinct folders.
A new characterization test ran against the unchanged worker before ZIP code was written. Tiny generated PNGs and a generated DOCX template exercised actual image preparation and DOCX generation, with only channel delivery mocked. Three top-level folders produced three independently identifiable reports and documents; with an invalid-image folder, two documents succeeded and one failure record remained. Batch status was PARTIAL; source cleanup ran after all folders.

Worker semantics preserved:
- Recursively collect images within each top-level folder; each folder has its own report/output directory.
- total_folders counts top-level directories; processed_folders counts successes; failed_folders counts failed reports.
- In-progress percentage counts successes/total. COMPLETED and PARTIAL report 100%; final completion event also reports 100%.
- No successes means FAILED; mixed results mean PARTIAL; no failures means COMPLETED. One folder-level failure does not abort the others.
- Failure reasons are persisted in FolderReport/FolderFailedPDF; the completion event currently has empty failed_details. No schema change is needed.

## Frozen API contract

Endpoint: existing authenticated multipart `POST /image/folder/upload/` (under the application's existing URL prefix).
Mode A: existing `files` + optional `paths`/`paths[]`; style/date/is_renamed_file semantics unchanged.
Mode B: exactly one file field `archive`, with optional style/date/is_renamed_file. Reject coexistence with files or either paths key, including empty keys. Filename extension and MIME are not trusted; actual ZIP structure is required.

Accept single-volume classic ZIP containing stored/deflated ordinary image entries and directory records. Reject encrypted entries, multipart/ZIP64 archive records, unsupported compression, links/devices, detectable DOS reparse/volume attributes, corrupt/truncated/CRC-invalid content and unsupported file extensions. Image rules match folder intake: nonempty, at most 50 MiB, extensions jpg/jpeg/png/bmp/gif/tiff/webp. No new image-content verification is imposed at intake; decoding remains the existing worker's responsibility.

Folder identity: preserve top-level folders and nested image paths. Normalize only image basenames with the existing normalizer. Empty directory records are validated but not materialized or counted. Repeated filenames in different logical folders are valid. A flat image archive maps to style or `uploaded`. Mixed loose images and foldered images are rejected rather than silently dropping loose images. A single wrapping folder remains one logical folder; no heuristic flattening.

Success: existing HTTP 201 fields batch_id, total_folders, message; one FolderBatch, same owner/source_folder/task contract. ZIP message counts the archive as one uploaded file. No source path is returned.
Validation: HTTP 400 with code and generic detail. `invalid_upload_mode` for mixed/multiple inputs, `invalid_archive` for invalid content/path/collision, `archive_limit_exceeded` for budget violations. Phase 01 filesystem conflict codes and generic HTTP 500 handling remain unchanged. Ordinary folder validation responses remain unchanged.

## ZIP threat model and budgets

Hostile sources: multipart fields, central/local ZIP metadata, entry names/types/sizes and compressed streams. Sensitive sinks: staging filesystem, batch persistence and task dispatch. Never use extract/extractall or recreate archive links. Preflight all entry destinations using Phase 01 validators/collision rules, then stream every image through Phase 01 open_upload_file (exclusive/no-follow POSIX descriptor traversal, Windows private ACL and reparse checks).

| Limit | Value | Rationale |
| --- | --- | --- |
| Compressed archive | 50 MiB | Matches existing per-file intake cap; below existing 500M proxy body ceiling |
| Archive entries | 1,000 including directories | Explicit bounded batch; no measured requirement justifies unbounded metadata/work |
| Central directory | 2 MiB | Bound ZipFile metadata allocation before object parsing using a bounded EOCD read |
| Expanded image | 50 MiB | Existing image business cap |
| Expanded batch | 200 MiB | Conservative four-times-upload staging budget, not the proxy ceiling |
| Expansion ratio | 100:1 per file | Reject suspicious expansion; ordinary compressed image payloads need little extra ZIP compression |
| Entry path | 1,024 characters; 255 UTF-8 bytes/component | Align intake path limit with Phase 01 cross-platform component restrictions |
| Streaming chunk | 64 KiB | Avoid loading expanded files into memory |

These are conservative initial API limits, not measured workload capacity claims. Increase only with workload evidence and resource review. Both metadata and streamed byte totals are bounded; CRC/decompression failure after earlier files triggers cleanup. Parsing allocation is bounded before ZipFile construction. ZIP64 is unnecessary for the allowed sizes/counts and archive-level ZIP64/multipart records are rejected.

Lifecycle: validate mode/style; exclusively create UUID job; preflight archive; stream safely; discover materialized folders; create batch; dispatch after commit. Intake failure cleans only this request's job and creates no batch/task. Existing database/broker failure behavior after completed staging is not redesigned.

## Tests and evidence

Command from backend:
```sh
python -B -m django test image_processor mail_download.tests --settings=image_processor.tests.settings --verbosity=2
```
58 tests collected: Windows 57 passed/1 POSIX-only skip; Linux 56 passed/2 Windows-only skips. Existing 31 Phase 01 tests remain unchanged. Coverage includes ZIP one/multiple/nested/flat folders, same names in distinct folders, canonical normalization, actual ZIP-to-worker DOCX generation, partial worker failure, metadata/stream limits, malformed/encrypted/unsupported archives, traversal/drive/UNC/reserved/control/NUL paths, special entries, duplicate/case/normalization/file-directory collisions, preflight-before-write, cleanup, owner, root, dispatch, authentication and redaction.
All fixtures are generated in temporary directories or memory. No production processing, running Celery broker, Redis, translation or LibreOffice. DOCX contents are reopened to verify embedded images; no claim of PDF/browser/visual UAT. Expected negative-fixture decoder logs and duplicate-entry warnings are test output only.
Existing PR CI already runs Image Processor discovery on ubuntu-latest and windows-latest for PRs targeting develop; no workflow change or duplicate CI is needed. Hosted exact-head results are recorded in the PR. Windows local direct framework pins match Phase 01, with some transitive differences; Linux local and hosted dependencies use repository requirements constraints.

## Self-review and sibling harvest

Required files: archive_upload.py owns bounded parsing/staging; folder_upload_view.py selects mode and retains common lifecycle; test_archive_upload.py verifies API/attacks/worker integration; test_multi_folder_worker.py characterizes unchanged processing; test_review_boundaries.py covers directory amplification and preparation-target parity; this document records contract/evidence. Phase 01 serializer/tests, worker, models, frontend, runtime dependencies and CI are unchanged. The shared path helper additionally normalizes server-resolved Windows extended drive/UNC spellings before containment comparison. A final Windows run exposed an intermittent false rejection in the existing concurrent-writer test; the small correction has a deterministic extended-path acceptance/outside-root rejection regression. All original Phase 01 assertions remain intact.

Discovery-only follow-ups:
- `backend/services/mail_download/downloader.py:70`: in-memory ZipFile.writestr uses attachment filenames without canonical archive-entry validation; potentially unsafe extraction names for recipients and unbounded aggregation. Medium conditional risk; separate Mail archive-hardening phase. No server extraction occurs here.
- `backend/image_processor/views/folder_docx_download_view.py:100`: output ZIP generation, not ingestion; no reusable inbound security boundary.
- Existing `_prepare_image` uses source.stem under one prepared directory. The blocking re-review fix now prevents both intake modes from admitting equivalent preparation targets within one logical folder. No worker rewrite; distinct logical folders remain independent.
- Existing completion events omit failed_details; persisted folder failure records remain the authority. Existing broker/template/setup errors and task retry semantics are not new ZIP defects.
- Staging 0777/0775 ownership/recursive chmod remains Phase 05/deployment hardening, explicitly excluded.

## Gates, rollback and stopping boundary

Requirement Freeze, Design, Implement, Self-review, Sibling Harvest, Adversarial Tests and affected Regression are complete locally before commit/push. Whole-backend syntax and scoped heuristic/diff checks are recorded with PR evidence. No configured backend lint/typecheck, no changed frontend/container build surface, no migrations.
Rollback: revert this Phase 02 commit to remove archive mode while preserving merged Phase 01 containment and ordinary folder uploads. No data migration. Phase 03 UI is NOT STARTED. Stop after PR verification for human review; do not merge or deploy.

## Blocking re-review fixes

Resource amplification: ZIP entry count did not count implicit parent directories. Preflight now allows at most 8 directory levels (logical style plus seven nested inspection groupings) and 1,000 unique case-folded directory identities across the archive. These conservative limits provide headroom above the characterized style/nested/image structures while preventing directory amplification beyond the existing 1,000-entry budget; no measured deeper workload is claimed. The filename is excluded from depth, explicit directory records include themselves, and flat mode includes its generated style/default folder. Even ignored empty directory records are budgeted conservatively. Tracking stops before adding identity 1,001; no oversized set is built. Rejection uses archive_limit_exceeded before open_upload_file, then cleans the request job.

QC report integrity: one shared preflight predicts the worker's constant-.jpg output from the final normalized filename stem, case-folded and scoped to the logical top-level folder. Both folder and ZIP modes reject duplicate preparation targets before any file write or dispatch, including differing source extensions, case aliases and normalized-name aliases. Different logical folders remain valid. Folder mode returns the existing upload_destination_conflict; ZIP mode returns generic invalid_archive. Original Phase 01 tests remain unchanged.

Tests cover exact depth/count limits, excessive implicit directories using two small file entries, bounded incremental tracking, no file-writer invocation, no new batch/task, response redaction, cleanup and preservation of an existing successful job. Both naming modes and both intake modes exercise all preparation collision variants. Existing nested/success and actual worker tests remain green.

## Separate HIGH date/output-path remediation — CONFIRMED, NOT IMPLEMENTED

QUEUED AS SEPARATE HIGH REMEDIATION — NOT IMPLEMENTED.
The unchanged request date flows from folder_upload_view.py:49 to process_image.py:564-566. Only spaces are replaced before joining docx_filename beneath folder_output_dir. _generate_docx creates parent directories and writes the DOCX at lines 365-371 without resolved output containment.

Isolated Linux replay on the review-fix tree: generated one 8x8 PNG and a one-table DOCX template, created a temporary in-memory test batch, invoked the real worker with date="../../../../escaped", and mocked channel delivery only. Before execution, the predicted output was asserted to remain within the disposable sandbox. Result: status COMPLETED; actual output was sandbox/output/escaped.docx rather than sandbox/output/<batch>/A/...; reopening the DOCX verified one embedded image. Temporary sources, outputs and database were discarded. No production filesystem or service was accessed. The probe script is an external review artifact, not a PR source/test change.

This permits generated report writes outside their intended output/report directory under the application identity and risks cross-report overwrite. A separate HIGH phase must validate date/business input and enforce contained output destinations with a regression proving rejection/no external write. It is pre-existing in the unchanged worker and separable from these intake guards. PR #3 does not fix it; passing intake tests is not production release approval.
