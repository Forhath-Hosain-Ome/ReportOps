# Isolated deployment readiness

Use only for the approved fresh UAT and Production validation sequence. It is not
an adoption procedure for an old database. Do not use `--fake-initial`.

## Immutable images and build contexts

From the repository root, build once:

```sh
docker build -f deploy/Dockerfile.backend -t uqgu-backend:REVISION .
docker build -f deploy/Dockerfile.frontend -t uqgu-frontend:REVISION .
```

Record image IDs/digests and build-context/source identity. Promote the same image
IDs to both environments; configuration, credentials and data remain separate.
Dockerfile-specific ignore files allow application source and approved templates
while excluding environment files, private state, logs, databases and build caches.

## Environment files and secrets

Create two private directories outside Git/build contexts. Use `environment.example`
as the non-secret Compose input template. Give each environment different database
and Redis passwords, Django signing keys and valid Fernet field-encryption keys.
Do not copy UAT secrets or writable state into Production.

Each secrets directory must contain `postgres_password`, `redis_password`,
`django_secret`, `field_key`, `redis_acl`, `edge_certificate.pem`, `edge_key.pem`.
The Redis ACL file defines an authenticated default user with its environment's
Redis password. Protect secret and backup files with host filesystem permissions.
Docker Compose mounts only the relevant secret files into each service.

The private runtime.env contains POSTGRES_DB, POSTGRES_USER, PUBLIC_ORIGIN and
DJANGO_ALLOWED_HOSTS (explicit comma-separated hosts; no wildcard). Never place
passwords in it. Settings read password/key files under /run/secrets.

Render the appropriate Nginx template by substituting only SERVER_NAMES with the
approved hostnames/IPs. Do not perform unrestricted environment substitution:
Nginx variables such as $host must remain intact. Production uses HTTPS; provide
a valid server certificate/key and establish trust on validation clients without
bypassing browser certificate warnings. Retain its CA certificate outside images.

## Compose invocation

Always supply `--env-file` explicitly; never inherit the repository's root .env.
Use compose.base.yaml plus exactly one environment overlay, with matching `-p`:

| Project | Overlay | Edge |
| --- | --- | --- |
| uqgu-uat | compose.uat.yaml | 127.0.0.1:18080 |
| uqgu-production | compose.production.private.yaml | 127.0.0.1:18443 HTTPS |
| uqgu-production, after R1-R17 | compose.production.lan.yaml | specified LAN IP:18443 HTTPS |

Example prefix from the repository root (append the intended command):

```sh
docker compose --env-file /private/uat/compose.env -p uqgu-uat -f deploy/compose.base.yaml -f deploy/compose.uat.yaml config --quiet
```

Do not combine private and LAN overlays. Do not add external volumes, global
container names, source bind mounts, or published database/Redis/backend ports.
pgAdmin is intentionally absent. Named volumes/networks receive the project prefix.
Backend and worker share media/staging/logs only inside their environment.

## Initialization and readiness

1. Validate the resolved configuration, writable-state disjointness and secret
   exclusions. Inspect only redacted configuration evidence.
2. Start postgres and redis; wait for their health checks.
3. Using `run --rm backend python manage.py ...`, run `check`,
   `makemigrations --check --dry-run`, and `migrate --plan`. These dry-run commands
   do not generate migrations. Apply only reviewed committed migrations with
   `migrate --noinput`, then run `migrate --check` and `image_processor_preflight`.
4. Start backend, worker, beat and edge. Normal startup never installs packages,
   generates/applies migrations, or creates users. Provision synthetic accounts
   explicitly without logging their credentials.
5. Verify real Redis task consumption, PostgreSQL session coordination, shared
   storage, upload/partial/failure/retry/recovery, authoritative DOCX/PDF downloads,
   settings, authenticated owner-scoped WebSockets and safe retention.
6. Restart and verify persisted records/artifacts.
7. Quiesce API writes, drain work, stop worker/beat, and create a consistent
   PostgreSQL backup plus media/staging backup. Restore into separate validation
   storage/network and verify records/artifact bytes. Backup creation alone fails
   the restore gate. Never use UAT backups as Production seed data.
8. Stop UAT while retaining volumes. Repeat from fresh Production state using
   the same application images and the private Production overlay.

No automatic runtime `makemigrations`, pip installation, or destructive adoption
is permitted. Do not use test-only migration modules for deployment initialization.

## LAN exposure and rollback

Only after Production R1-R17 pass, select the LAN overlay and recreate **only edge**
with `up -d --no-deps --force-recreate edge`. Keep other services/volumes unchanged.
Verify the intended LAN port plus absence of direct DB/Redis/backend/pgAdmin
publication, then perform second-device frontend/API/WebSocket checks. Host-only
testing cannot satisfy the second-device gate. No firewall changes, router port
forwarding or Internet publication are part of this phase.

If an exposure gate fails, recreate edge with the private overlay. If runtime
checks fail, stop the affected project without deleting volumes. Never use
`down -v`, prune shared Docker resources, or reverse schema over retained data as
an automatic rollback. Preserve verification evidence and give a factual NO-GO.
