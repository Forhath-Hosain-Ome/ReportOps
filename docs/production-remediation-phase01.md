# Phase 01 — Image upload filesystem containment

## Requirement, design and scope

Primary question: can a client upload write outside its server-created job directory?
The user authorized Phase 01 implementation and PR delivery, then requested the fixes in PR #2 comment 5558536602. Acceptance: preserve legitimate upload layout/ownership/task arguments; reject traversal, absolute paths, links and collisions; create no batch or task on rejected input; clean only a newly created job after failed writes.

No ZIP or multi-folder feature expansion, frontend, dependency, schema, worker or deployment changes. Existing multi-folder payloads remain characterized. The only CI addition runs this boundary on Windows and Linux.

Validate metadata and actual filenames before normalization, then validate exact final destinations. Preserve `/tmp/batch_uploads/<uuid>` for worker/cleanup compatibility. Create the job with atomic `mkdir(mode=0700)` without `exist_ok`. Create files with `O_CREAT|O_EXCL`, mode 0600. No process-wide umask changes are needed: an existing umask can only remove permission bits.

POSIX traversal opens each directory using `O_DIRECTORY|O_NOFOLLOW`, then uses `dir_fd` for mkdir/open; a replaced path cannot redirect the pinned descriptor. Windows uses canonical containment plus `lstat` reparse-point rejection after each parent mkdir and immediately before exclusive open. [Python 3.12.4+](https://docs.python.org/3.12/library/os.html#os.mkdir) supports private Windows mode-0700 mkdir ACLs; CI uses current Python 3.12. Windows file ACLs inherit the private directory ACL. A compromised application identity/host administrator is outside this request-input boundary; Windows does not claim POSIX descriptor-level protection against same-identity attackers.

## Repository safety and original finding

Base: `develop` at `3fb8aa87e40f537fedcaafccf4d69235a90d908e`; task branch: `fix/image-upload-containment`; PR: https://github.com/Forhath-Hosain-Ome/UQ_GU_Web_Summary/pull/2.
Work is isolated from `D:/Project/UQ_GU_Web_Summary`. Its staged extractor work, unstaged Docker/settings/Compose changes, and untracked architecture/environment/log files are preserved. `main` diverges substantially; `develop` is this phase's verified base.

On the unchanged base, legitimate upload passed but relative and absolute malicious styles returned HTTP 201. A separate replay loaded the base serializer/view and confirmed synthetic bytes were written outside the generated job, entirely within disposable sandboxes. The unchecked `style` join followed by rename caused the escape. The view also replaced the serializer's filename with another client filename; both are now validated.

## Review corrections and error contract

- Atomic job/file creation rejects existing objects without deleting them. Parent mkdir followed by atomic no-follow directory open verifies POSIX parents; Windows checks every newly created parent for all reparse points.
- No filesystem exception text or traceback is emitted in upload failure logs/responses. Logs carry a stable code and exception class; cleanup failure logs are generic.
- Destination/name collisions, including an existing UUID directory, return HTTP 400 with `code=upload_destination_conflict`. Existing input-validation status is retained rather than introducing HTTP 409. No automatic renaming or retry can overwrite files.
- Rejected filesystem destinations return HTTP 400 with `code=invalid_upload_destination`; unexpected failures return HTTP 500 with `code=upload_failed`. Serializer field errors retain the existing HTTP 400 format.
- CI runs actual `windows-latest` and `ubuntu-latest` jobs with pinned action commits, read-only repository permission, no persisted credentials and repository-constrained test dependencies.

## Verification

From `backend`, with test dependencies installed:
```sh
python -B -m django test image_processor mail_download.tests --settings=image_processor.tests.settings --verbosity=2
```
Tests use real multipart requests, serializers, ORM, temporary files and an in-memory SQLite database; Celery dispatch is mocked. No image processing, Redis connection or deployment credentials. Test-only table synchronization compensates for missing committed Image Processor migrations; migration repair remains Phase 05. Mail Download has no discovered test cases.

| Check | Result |
| --- | --- |
| Base reproduction | Two attack regressions fail on base; valid upload passes |
| Windows local suite | 31 collected; 30 pass; POSIX-only descriptor/mode test skipped |
| Linux local suite | 31 collected; 30 pass; Windows-only ACL test skipped |
| Cross-platform coverage | Real junctions/symlinks, concurrent exclusive writers, parent substitution during mkdir, collisions, traversal, validation and owner-scoped API consumers |
| Platform coverage | Linux parent swap before file open stays pinned; umask 0 still gives 0700/0600. Windows job/file ACL allows only owner (including OWNER RIGHTS), SYSTEM and Administrators |
| Logging | Injected absolute filesystem path absent from failure response and captured logs |
| Static checks | Whole-backend Python parse, diff whitespace and focused heuristic review |
| Hosted CI | Results recorded on PR #2 for its exact head; local results do not substitute for hosted Windows execution |
| Not applicable | No configured backend lint/typecheck; no frontend/container build changes |
| Not run | Production DB, Redis, rendering, browser UAT or full release qualification |

Linux local dependencies use `requirements.txt` constraints; Windows local direct framework pins match but some transitives differ. Both hosted jobs constrain the full installed test dependency closure. No dependency declaration changed.

## Self-review and sibling harvest

Runtime changes belong to input validation, containment and the final upload write. Tests/settings/URLs isolate the actual API; CI verifies OS behavior; this document records evidence. Worker discovery, cleanup root, task signature and batch ownership remain unchanged. Existing upload-root collisions, normalized-name conflicts, cleanup failures and concurrent creates are tested.

Separate follow-ups, not changed: Puma duplicate-counter filename collisions; mail ZIP entry-name safety; Image batch-detail prefix-based existence checks. The original heuristic scan found four pre-existing broad cleanup handlers; this review narrows the upload cleanup handler to OSError and records generic cleanup failure. Remaining worker/download cleanup issues do not authorize unsafe uploads.

## Operational triage and rollback

For HTTP 400 collision codes, ask the uploader to remove duplicate/case-aliased normalized names. Do not reveal staging paths or retry using overwrite. An unexpected UUID conflict should be investigated through restricted host access; retain the existing job. For `upload_failed`, inspect safe log categories and restricted storage capacity/permissions; a cleanup warning may require removal of abandoned jobs through established operations. Do not add absolute paths to customer-facing diagnostics.

No deployment is performed. After separate rollout authorization, use a small canary and monitor rejection/failure rates before expansion. Reverting this phase restores the vulnerability; prefer a forward fix or disabling uploads. No data migration is involved. Production ACL/identity/storage verification remains a release gate.

## Delivery state and phase queue

Requirement Freeze, Design, Implementation, Self-review, Sibling Harvest, Adversarial Tests and affected Full Regression: PASS on the review-correction diff before commit/push. PR remains subject to hosted CI and human re-review; evidence is tied to the current diff.

Phase 01: review corrections. Phases 02–09 (multi-folder/ZIP backend and frontend, JWT, migrations/startup, mail proxy, summary persistence, lint and release qualification): NOT STARTED.
Stop after this PR update. No merge or deployment is authorized.
