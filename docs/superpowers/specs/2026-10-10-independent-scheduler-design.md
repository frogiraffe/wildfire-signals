# Independent Free scheduler for public collection

## Purpose and evidence

The public collector already runs in GitHub Actions and enforces Cloudflare Free and a 55-minute publication interval. GitHub `schedule` events have recorded multi-hour gaps even while manual dispatch succeeds. GitHub documents that scheduled events may be delayed or dropped. The exact cause of a missing event is not exposed by the run list.

The goal is to keep automatic collection running while the user's computer is off, without enabling a paid service or making extra FIRMS downloads when GitHub's own schedule is healthy.

## Design

Create a separate Cloudflare Worker on the already confirmed Workers Free account. It has one Cron Trigger every 15 minutes, no public HTTP route, and a read/write binding to the existing public snapshot KV namespace. It reads only `current` and a short-lived `scheduler:last_dispatch` marker. When the last verified scan is at least 65 minutes old and no dispatch succeeded in the last 55 minutes, it calls GitHub's workflow-dispatch API. The request passes `force_collection=false`. The GitHub workflow retains its existing schedule, concurrency group, Free subscription check, 55-minute scan guard, provider calls, and KV publication limits. A manual UI dispatch remains a deliberate forced repair.

The Worker uses a fine-grained GitHub token scoped only to `frogiraffe/wildfire-signals` with repository Actions write permission. The token is a Worker secret, never committed or sent to chat. A separate Cloudflare deployment token scoped to this account and Workers editing is stored as a GitHub Actions secret for a manual deploy workflow. The deploy workflow checks the existing Cloudflare Free gate before deployment. Deployment is never automatic on a public pull request.

On absent `current`, the Worker may request a non-forced bootstrap run. On an invalid, future-dated, or unreadable pointer or dispatch marker, it fails closed and logs the error. It records a 60-minute TTL dispatch marker only after GitHub accepts the request. GitHub's collector remains the final authority on duplicate scans and cost. KV eventual consistency may permit an occasional duplicate dispatch; the collector must skip extra provider calls and writes if a newer pointer is visible.

## Cost and acceptance

The Worker has one of the five Cron Trigger slots available on Workers Free, about 96 invocations and at most 192 KV reads per day plus roughly 24 marker writes when collection is stale. It makes no paid API calls. Existing map traffic remains the larger KV read use. Free limits and account plan must be checked at deployment; if they cannot be verified, deployment stops. Account-wide future changes cannot be guaranteed by repository code.

Acceptance requires tests for fresh, stale, missing and malformed pointers, recent dispatch markers, failed GitHub API calls, and dispatch payload. A live non-forced workflow dispatch must skip within 55 minutes of a publication. After credentials are installed, a live Cron Trigger and GitHub run must be observed; source-only deployment is not a resolved scheduler incident. Seven-day continuity remains a later 1.0 gate.
