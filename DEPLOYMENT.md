# DIGITAL DIARY — self-managed launch guide

This project keeps FastAPI, PostgreSQL, and the existing API routes. The deployment adds a private Supabase Storage bucket for case files, a Dockerized API behind Caddy/HTTPS, Flutter web/mobile build configuration, and optional per-officer Razorpay subscriptions.

Supabase hosts the database and file bucket in this plan; it does not run this Python/FastAPI service. Supabase Edge Functions use a Deno/TypeScript runtime, so replacing the existing API with them would require a rewrite.

## Recommended low-cost pilot path

For a first cohort of 50–100 officers, use:

- **Supabase Free** for a staging or limited pilot using synthetic/non-sensitive cases. The current Free limits include 500 MB database, 1 GB file storage, and 5 GB egress; projects with low activity can pause after a week, and Free does not include automatic database backups. Use the Supabase-issued **Session pooler** connection string on an IPv4-only VM; use the direct endpoint only when the host supports IPv6. Keep TLS enabled (`DB_SSL=true`).
- **One 2 vCPU / 4 GB DigitalOcean Droplet** in Bangalore for the API and Caddy. This is a simple starting point, not a guarantee of capacity. Scale after measuring real document/OCR workloads.
- **Cloudflare Pages** (or another static host) for the Flutter web build, on a separate `app.your-domain` hostname. Put the API on `api.your-domain`.
- Build Android and iOS from Flutter. The mobile clients call the same HTTPS API and open Razorpay’s hosted subscription checkout in the system browser.

Indicative baseline for the pilot: a 2 vCPU/4 GB DigitalOcean Basic Droplet is currently listed at $24/month; Supabase Free and static hosting on Cloudflare Pages add no base fee, so budget roughly **$24/month before taxes, domain, AI-provider use, and backup costs**. Confirm vendor checkout prices and regional availability before purchasing. This saves money but transfers backup and availability responsibility to you.

This single-API-node deployment is for a pilot. Supabase Free is not an appropriate durable production database/storage tier for operational police records without an approved backup and recovery plan: low-activity pause, no automatic database backups, and the small storage/egress quotas can interrupt service. Confirm department approval and test an independent encrypted backup/restore before any real case data. For thousands of concurrent users, upgrade the data tier, instrument and load-test representative document workflows, then add API replicas and background workers, right-size database connection limits, and tune AI-provider quotas. Do not assume the pilot VM can handle thousands concurrently.

## Free demo deployment (synthetic data only)

For a no-domain demo, use the included `render.yaml` to create the FastAPI service on Render Free, keep the existing Supabase Free database and private `case-files` bucket, and publish the Flutter web build to Cloudflare Pages using Direct Upload. Render gives the API an `onrender.com` URL; Pages gives the frontend a `pages.dev` URL. No domain purchase is needed. This setup is for a demo only: Render Free can sleep after 15 minutes idle, takes about a minute to wake, can restart, has no persistent disk, and runs one small instance. Supabase Free can pause after inactivity and does not include automatic database backups. Use only synthetic cases and sample documents.

1. Put the source in a **private GitHub repository**. Review `.gitignore` and confirm `.env`, `src/.env`, local uploads, generated files, and signing keys are not staged. Never commit actual case records, database exports, or secrets.
2. In Render, choose **New → Blueprint**, connect the private repository, and deploy `render.yaml`. When prompted, enter the values for `DB_CONNECTION`, `JWT_SECRET_KEY`, `CORS_ORIGINS`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, and `GEMINI_API_KEY` as Render environment variables. Reuse the Supabase Session pooler URI and secret key already configured for this project; do not paste them into chat or a committed file. Generate a fresh random JWT secret at least 32 characters long.
3. Create a Cloudflare Pages project named `digital-diary-demo` (or another available name). Build the web app locally from `frontend/`:

   ```powershell
   flutter pub get
   flutter build web --release --dart-define=API_BASE_URL=https://YOUR-RENDER-SERVICE.onrender.com
   ```

   In Cloudflare Pages, choose **Direct Upload** and upload `frontend/build/web`. Cloudflare's Direct Upload project cannot later be converted to Git integration; create a separate project if you later want automatic builds.
4. Set Render's `CORS_ORIGINS` to the exact Pages origin, such as `https://digital-diary-demo.pages.dev`, then redeploy the API. Do not include a trailing slash or use `*`.
5. After deployment, check `https://YOUR-RENDER-SERVICE.onrender.com/health/live` and `/health/ready`. Then register a demo account and test with synthetic records and non-sensitive documents only. The database schema is already migrated; for future schema updates, apply the checked-in Alembic migrations before deploying code that depends on them.

Render Free services sleep after inactivity and can restart; generated files in their filesystem are temporary. The app must continue to store case uploads in the configured private Supabase bucket. The Render health check uses `/health/live`; use `/health/ready` yourself to confirm the database connection.

## Before using real case data

Get the relevant department/agency approval for the selected cloud region, data handling, backups, and third-party AI processing. Use synthetic cases until approval is clear. Keep the Supabase secret key, database password, JWT secret, AI keys, and Razorpay secrets only in the server secret environment. Never put them in Flutter, a public repository, or a browser build.

The Supabase database backup does **not** back up Storage objects. Keep a separate encrypted off-site copy of case files and rehearse restoring both database and files before production use. Supabase Storage currently does not provide object versioning, so do not treat the bucket as the only copy.

## 1. Prepare Supabase

1. Create a Supabase project. Choose a region approved for the data and closest to the API host. For the Free pilot, use synthetic/non-sensitive records until you have confirmed a suitable backup and recovery setup.
2. Set a strong database password and retain it in a password manager.
3. In **Connect**, copy the Session pooler connection string for an IPv4-only VM. Preserve the Supabase username/host/port, URL-encode reserved characters in the password, and use `postgresql+asyncpg://` as the SQLAlchemy scheme.
4. In **Storage**, create a **private** bucket named `case-files`. Do not expose the bucket publicly. The API generates short-lived signed download URLs.
5. In **Project Settings → API Keys**, create/copy a server-side `sb_secret_...` key and put it in `SUPABASE_SECRET_KEY`. The API uses this key only in the `apikey` header. The application retains compatibility with the legacy `service_role` JWT under `SUPABASE_SERVICE_ROLE_KEY`; prefer the newer secret key for new deployments. Do not use the publishable/anon key for server writes.
6. Enable database backups and define a separate encrypted object-storage backup/export schedule. Test a restore to a separate project before migrating live records.

The app migration bootstraps a new database and adopts several older schema columns. For an existing deployment, take a database backup first and rehearse the migration on a restored copy. Moving the database does not move local evidence files automatically; copy those files to the private bucket and update their database references before retiring the old host.

## 2. Prepare the server and domain

1. Create an Ubuntu LTS 2 vCPU/4 GB VM, preferably in Bangalore, and point `api.your-domain` to its static IP.
2. Restrict inbound traffic to SSH from your admin IP plus TCP 80/443. Do not open port 8000 or PostgreSQL to the public internet. Use SSH keys, disable password SSH, and keep the OS patched.
3. Install Docker Engine and the Docker Compose plugin using Docker’s official Ubuntu instructions.
4. Copy this repository to the server using a private deployment method. Do not upload `.env`, evidence folders, database dumps, or signing keys to a public Git repository.
5. Copy `.env.production.example` to `.env.production`, then fill every value. Generate a random `JWT_SECRET_KEY` of at least 32 characters. Use exact web origins, e.g. `https://app.your-domain`; do not use `*`.
6. Set the Supabase URL, pooler connection, `DB_SSL=true`, and Storage values. Keep `DB_POOL_SIZE` and `DB_MAX_OVERFLOW` low per API process at first. Every replica gets its own pool, so total possible DB connections are `(pool size + overflow) × replicas`.
7. Set `API_DOMAIN=api.your-domain` in `.env.production`. Caddy obtains and renews the HTTPS certificate automatically after DNS points to the server and ports 80/443 are reachable.
8. Add AI credentials in the server environment. Confirm the configured model names and usage limits with the providers before launch.

## 3. Apply schema and start the API

From the repository root on the server:

```bash
docker compose --env-file .env.production -f compose.production.yaml build
docker compose --env-file .env.production -f compose.production.yaml run --rm api alembic upgrade head
docker compose --env-file .env.production -f compose.production.yaml up -d
docker compose --env-file .env.production -f compose.production.yaml ps
```

Check `https://api.your-domain/health/ready`. It should return `{"status":"ready"}`. Review logs with:

```bash
docker compose --env-file .env.production -f compose.production.yaml logs --tail=200 api proxy
```

The API container is non-root, read-only, and only exposed through Caddy. Generated working documents use temporary storage; persistent case files go to Supabase Storage. Keep Docker and OS security updates current.

## 4. Build and publish Flutter clients

From `frontend/`, after installing the Flutter SDK and dependencies:

```bash
flutter pub get
flutter build web --release --dart-define=API_BASE_URL=https://api.your-domain
```

Publish `frontend/build/web` to Cloudflare Pages and set `https://app.your-domain` as a CORS origin in `.env.production`; restart the API after changing it.

### Android

Before release, choose a permanent reverse-domain application ID (the current `com.example.cyber_case_diary` is a placeholder), create and securely back up a release keystore, and create `frontend/android/key.properties` locally:

```powershell
keytool -genkey -v -keystore frontend/android/app/upload-keystore.jks -keyalg RSA -keysize 2048 -validity 10000 -alias upload
```

Keep the keystore offline in a second secure backup. `storeFile` below is resolved relative to `frontend/android/app`.

```properties
storePassword=YOUR_STORE_PASSWORD
keyPassword=YOUR_KEY_PASSWORD
keyAlias=YOUR_KEY_ALIAS
storeFile=upload-keystore.jks
```

`key.properties` and common keystore files are gitignored. Never lose the signing key or commit it. Then build on a machine with Android SDK installed:

```bash
$env:ANDROID_APPLICATION_ID = "com.yourorg.digitaldiary"
flutter build appbundle --release --dart-define=API_BASE_URL=https://api.your-domain
```

The output is `frontend/build/app/outputs/bundle/release/app-release.aab`. Use the same application ID and signing lineage for every update.

### iOS

Build on macOS with Xcode. Set a permanent Apple Developer Team and bundle identifier in Xcode (`Runner` target → Signing & Capabilities), configure App Store Connect, then:

```bash
flutter build ipa --release --dart-define=API_BASE_URL=https://api.your-domain
```

The current bundle ID is a placeholder. Apple signing and store enrollment must be completed in your Apple account.

## 5. Configure Razorpay subscriptions

The app uses a monthly Razorpay Plan and does not hard-code the INR price. Create the monthly plan in the Razorpay Dashboard after deciding the price, then put its Plan ID and API credentials into the server environment. Keep `BILLING_ENFORCED=false` while configuring and validating in Test Mode.

Set the Razorpay webhook URL to `https://api.your-domain/billing/razorpay/webhook`, copy the webhook secret into `RAZORPAY_WEBHOOK_SECRET`, and subscribe to subscription lifecycle events used by the dashboard (including activation, charge, pause/halt, cancellation, and completion). Confirm signatures and subscription state transitions in Test Mode before switching to Live Mode.

`RAZORPAY_TOTAL_COUNT` defaults to 120 monthly billing periods (10 years); change it if the chosen Razorpay plan requires a different term. Once the live plan, webhook, and payment flow are validated, set `BILLING_ENFORCED=true` and restart the API. Until then, payment screens can be checked without blocking case access. The hosted checkout URL works in web and mobile clients; the app updates access from verified server webhooks, not a client-side success claim.

## 6. Operations checklist

- Monitor `/health/live`, `/health/ready`, container restarts, CPU/memory, database connection count, storage use/egress, AI-provider errors, and Razorpay webhook delivery.
- Alert on repeated AI timeouts, DB pool timeouts, disk pressure, failed backups, and failed webhook deliveries.
- Keep an encrypted database backup and a separately tested object backup. Document restore steps and retention.
- Keep production case files private and use least-privilege staff access. Add institution-approved account onboarding/identity verification before opening registration broadly.
- Set request/file size limits appropriate to actual scans. The reverse proxy currently allows 22 MB request bodies; routes may have lower per-file limits.
- Before advertising capacity for thousands of users, run load tests with realistic OCR/AI, uploads, concurrent diary generation, and peak login traffic. Add a background queue for long-running scans/generation, then add API replicas and tune Supabase connection pooling. Monitor provider rate limits and costs.
- Roll out schema changes using Alembic, with a backup and rollback plan. Do not edit production tables manually as the standard release process.

## Useful references

- [Supabase database connection methods](https://supabase.com/docs/guides/database/connecting-to-postgres)
- [Supabase pooling and connection limits](https://supabase.com/docs/guides/database/connecting-to-postgres/pooling-and-limits)
- [Supabase production checklist](https://supabase.com/docs/guides/deployment/going-into-prod)
- [Supabase backups](https://supabase.com/docs/guides/platform/backups)
- [Supabase pricing and quotas](https://supabase.com/pricing)
- [DigitalOcean Droplet pricing](https://www.digitalocean.com/pricing/droplets)
- [Razorpay subscription API](https://razorpay.com/docs/api/payments/subscriptions/create-subscription)
- [Razorpay subscription webhooks](https://razorpay.com/docs/webhooks/subscriptions)
- [Razorpay webhook signature verification](https://razorpay.com/docs/webhooks/validate-test/)
