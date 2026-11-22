# Phase 02.5 — Image Processor output containment

## Requirement and design

Existing branch `fix/image-processor-output-containment` is clean and equals develop and the locally recorded origin/develop at `f0ace9d407607c5129970bbe077cc3b16ef4ee97` (PR #3 merge). No branch recreation or rebase. Remote state has not been queried.

Baseline reproduction: the existing isolated investigate_date_output.py replay ran against this unchanged SHA with an in-memory database, generated 8x8 PNG and DOCX template, and mocked channel delivery. Date ../../../../escaped caused the real worker to write output/escaped.docx outside output/<batch>/A, return COMPLETED, and persist the escaped path. The generated document contained one image. All files were inside a disposable sandbox.

Expected behavior:
1. Date is optional. Empty or surrounding-whitespace-only input retains the existing no-date filename. Otherwise accept only an actual calendar date in ASCII YYYY-MM-DD, years 0001–9999, after trimming surrounding whitespace. Existing date-picker values remain unchanged. Reject malformed dates, traversal, separators, controls within the date and non-string worker inputs.
2. Both folder and ZIP intake reject invalid dates with HTTP 400, code invalid_date and generic detail before staging, batch creation or task dispatch.
3. Direct/queued worker calls enforce the same rule. Invalid date or filename components fail the folder through the existing report/batch failure lifecycle, with no output write; valid folders retain existing success/partial semantics and source cleanup.
4. Keep the existing <OUTPUT_DIR>/<batch>/<folder>/<label>_<folder-with-underscores>_dated on <date-or-no-date>.docx layout. Validate folder, label, batch and final filename using existing cross-platform component rules (including the 255 UTF-8-byte filename boundary). Do not sanitize traversal into another identity.
5. Resolve and check every output destination under the configured trusted output root. Reject links/reparse points, outside destinations and pre-existing target files; never overwrite another report or prepared image. Reuse Phase 01 exclusive/no-follow writes. Preparation and DOCX generation share this boundary. Parent creation is checked before and after; Windows retains the established application-owned-directory assumption, not protection against a compromised same-identity process.

One local boundary fix; no frontend, schema, dependencies, infrastructure, upload-staging permission changes, Phase 03, merge or deployment. OUTPUT_DIR is trusted application configuration. Rollback is a revert of this phase; no migration.

Verification plan: baseline exploit replay; date/API parity; real-worker valid/invalid dates and persisted paths; invalid components, exact filename limits, existing targets and links; complete Phase 01/02 image_processor and mail_download.tests regression suite. Tests use only generated fixtures and isolated settings. No services, external credentials, production files or dependency downloads.

## Review, sibling comparison and verification

Changed files: output_paths.py owns the shared date/filename/output boundary; folder_upload_view.py rejects invalid dates before side effects; process_image.py validates worker metadata and uses contained exclusive writes; test_output_containment.py supplies 11 focused tests; this document freezes the contract and evidence. No Phase 01/02 source or test assertions were rewritten, and no dependencies, settings, database migrations, frontend or deployment files changed.

Sibling harvest: upload_paths.py supplies cross-platform validation, resolved containment, Windows namespace handling and exclusive/no-follow writes. Folder DOCX/PDF download resolvers use resolved containment and consume persisted relative paths; their code is unchanged. The existing date picker submits ISO dates. No other callers of _prepare_image or _generate_docx exist. The full Phase 02 worker tests exposed Windows short-name versus long-name aliases; write destinations now remain relative throughout, and persisted paths use the resolved media root. File output modes remain 0644 on POSIX using descriptor chmod, and report directories retain 0755; staging permissions are unchanged.

Final Windows 11 / Python 3.12.14 / Django 6.0.3 checks, using the existing offline Phase 01 dependency directory and isolated settings:

```text
python -B -m django test image_processor mail_download.tests --settings=image_processor.tests.settings --verbosity=2
69 tests; 68 passed; 1 existing POSIX-only descriptor-race test skipped; exit 0.
```

All 11 new tests passed in that final regression run. Coverage includes exact calendar/UTF-8 filename bounds, invalid types/paths, both upload modes before side effects, resolved outside paths, real directory/file links, existing targets, real DOCX contents and persisted locations, worker failure records, independent-folder partial success, and source cleanup. The original exploit is now rejected with no output directory or persisted output path. Phase 01/02 tests are included without changes.

Backend AST syntax: 273 Python files passed. git diff --check passed. Governance scanner: five changed files, no architecture-significant signals or mechanical findings; no formal ADR or policy file exists in this checkout. Scoped security scanner: no Critical/High signals; one existing broad exception/pass in the outer worker failure-reporting fallback remains unchanged. It is not a new output-boundary bypass: the task still raises after that fallback. Manual source-to-write and failure-path review found no unresolved Phase 02.5 defect. No new architecture decision or waiver is required for this local fix.

Linux/POSIX execution and hosted CI have not run in this task. The existing PR workflow covers Linux and Windows when remote execution is authorized. No dependency installation, browser/PDF conversion UAT, production or service execution is claimed. Existing-target collisions intentionally fail instead of overwriting; partial newly created artifacts after I/O failure are not published as completed reports. Application-owned output directories remain a trust assumption; same-identity filesystem tampering and deployment ownership hardening are outside this phase.

| Gate | State | Evidence |
| --- | --- | --- |
| Requirement Freeze | PASS | User-ordered Phase 02.5 contract above |
| Design | PASS | Existing boundary helper reuse; no architecture/dependency expansion |
| Implement | PASS | Five scoped files |
| Self-review | PASS | Full diff and error-path audit |
| Sibling Harvest | PASS | Intake, worker, download consumers and date picker inspected |
| Adversarial Tests | PASS on Windows | All 11 added tests passed |
| Full Regression | PASS on Windows | 68 passed, one existing POSIX-only skip; Linux pending |
| PR | BLOCKED | User also prohibits external-system and credential access; remote exception needed |

Delivery verdict: locally verified for Windows, not merge/deployment-ready. Phase 03 and deployment remain paused until this fix is reviewed and merged. No remote access, merge or deployment was performed.
