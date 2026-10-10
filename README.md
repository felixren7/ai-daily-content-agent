# AI Daily Content Agent

[English](README.md) | [简体中文](README.zh-CN.md)

AI Daily Content Agent is an open-source Python service that discovers recent AI developments or
selects an evergreen frontier concept, verifies the available evidence, creates a source-grounded
social post, applies a deterministic quality gate, and either queues the post for review or
publishes through explicitly configured adapters.

The default configuration is deliberately safe: it uses a deterministic local template generator,
stores output as `pending_review`, and never contacts a social publishing API. DeepSeek and other
OpenAI-compatible providers can be enabled through environment variables.

## Architecture

```mermaid
flowchart TD
    A[Official RSS / arXiv / GitHub] --> B[Concurrent collectors]
    B --> C[Sanitize and normalize]
    C --> D[URL + hash + title + semantic deduplication]
    D --> E[Configurable topic ranker]
    K[Concept database] --> F[Mode and topic selection]
    E --> F
    H[(SQLite / PostgreSQL-ready SQLAlchemy)] --> D
    H --> E
    F --> G[Fact checker and evidence boundary]
    G --> I[LLM provider abstraction]
    I --> J[Quality gate]
    J --> T[Cached English / Chinese variants]
    T --> L{Dry run / approval / scheduled publish}
    R[Operator dashboard] --> L
    L --> M[X adapter]
    L --> N[LinkedIn adapter]
    L --> O[Telegram adapter]
    L --> P[Webhook adapter]
    L --> H
    Q[APScheduler + file lock] --> B
```

Pipeline steps are logged as `FETCH`, `NORMALIZE`, `DEDUP`, `RANK`, `VERIFY`, `GENERATE`,
`QUALITY_CHECK`, `PUBLISH`, and `DONE` or `FAILED`. Every log entry contains a `run_id`.

## What is implemented

- News mode with seven first-party/high-authority RSS feeds, arXiv, and GitHub Search.
- Frontier concept mode with a persisted, non-repeating concept catalog and curated references.
- Mixed mode using either news-importance selection or deterministic alternation.
- Exact and hashed n-gram/concept-vector similarity deduplication, plus publication-history checks.
- Configurable weighted ranking for recency, source quality, importance, novelty, technical
  relevance, and social interest.
- Evidence extraction, per-claim support flags, source preservation, and confidence thresholds.
- Template, DeepSeek, OpenAI, and generic OpenAI-compatible LLM providers.
- Optional, separately configured compatible image-generation endpoint.
- Quality checks for sources, confidence, unsupported claims, hype, length, unexpected numbers,
  clarity, grammar, and similarity with previous output.
- Review workflow, publication audit history, daily scheduling, concurrency protection, JSON logs,
  health endpoints, Docker deployment, and a complete CLI.
- Responsive bilingual operator dashboard with run-now, five-second progress refresh, evidence
  review, source-grounded regeneration, approval, and guarded immediate or scheduled publication.

## Quick start with Docker

### Prerequisites

- Docker Desktop, or another Docker environment with Compose v2.
- Port `8000` available.
- Python 3.12 only if you run the project outside Docker.

Check Docker:

```bash
docker --version
docker compose version
```

Create the local environment file:

```bash
cp .env.example .env
```

That command is only for first-time setup. If `.env` already exists, back it up or edit it directly
rather than overwriting existing keys and settings. This form is always safe:

```bash
test -f .env || cp .env.example .env
```

The default `.env.example` already uses the safe settings:

```dotenv
LLM_PROVIDER=template
DRY_RUN=true
AUTO_PUBLISH=false
PUBLISH_PLATFORMS=
```

Build and start:

```bash
docker compose up --build -d
docker compose ps
```

The `app` service in `docker compose ps` should report `healthy`. Then run the agent once:

```bash
docker compose exec app python -m app.cli run --dry-run
```

The final command fetches live public feeds, stores normalized articles in SQLite, creates one post,
prints it to the terminal, and skips all publication calls. Expected progress resembles:

```text
Fetching AI sources...
Found 42 articles
Normalizing and storing articles...
Removing duplicate stories...
Removed 7 duplicates
Ranking 35 topics...
Verifying sources...
Selected: Example topic
Generating post...
Evaluating content quality...
Quality score: 95
Saving post and evaluating publication mode...
DRY RUN — publication skipped.
DONE
```

Feed counts vary. One failed source is reported as a warning and does not abort other collectors.
If every current source is unreachable or no topic passes verification, the run is marked `failed`
rather than creating an unsupported post.

Health endpoints:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/posts
curl http://localhost:8000/runs
```

### Open the operator dashboard

Once the service is running, open [http://localhost:8000](http://localhost:8000).

The page reads the same SQLite records as the CLI and lets you inspect extracted facts and source
links, move through the review queue, start the agent, regenerate a draft from feedback, and approve
an English or Chinese publication variant. After approval, choose immediate publication or a
persisted future time. The page refreshes run progress every five seconds; the delayed-publication
dispatcher checks due work every 30 seconds. With the default `DRY_RUN=true`, both paths exercise
the guarded workflow but make no social API call. Immediate and scheduled publication are mutually
exclusive; revision or regeneration cancels the old persisted schedule before a replacement draft
is created.

Day-to-day operation does not require a terminal:

1. Confirm `Dry run` is still on at the top of the page. Even if you press publish, no social API
   is called.
2. Press `Run now` to generate a new post manually. This really executes collection, deduplication,
   ranking, verification, and LLM generation; with DeepSeek configured it consumes one model call.
3. The page refreshes every five seconds. `Today's run` shows fetched counts, duplicates, candidate
   topics, and the current stage without a manual reload.
4. Press `中文` in the top right to switch the interface to Chinese. When the selected post has no
   Chinese variant, the configured LLM translates it once, validates that source URLs, numbers, and
   fact count are preserved, and caches the result in the database; later switches reuse the cached
   variant and cost nothing. The offline `template` provider cannot translate.
5. Read the post body, then check `Verified facts` and `Source evidence` rather than trusting the
   quality score alone.
6. Press `Regenerate` and give specific feedback to rewrite a draft. The system may use only the
   stored facts and sources, re-runs the quality gate, creates a new draft, and marks the old one
   `superseded`.
7. Press `Approve & queue` once you are satisfied. This only changes the status to `approved`; it
   publishes nothing.
8. After approval, choose `Publish now` or `Schedule publish`. Scheduling persists the exact time
   and language variant in SQLite, and the background dispatcher scans for due work every 30
   seconds. The two paths are mutually exclusive; sending a scheduled post back for revision or
   regeneration cancels the old schedule automatically.
9. With `DRY_RUN=true`, both immediate publication and due scheduled publication are recorded as
   skipped and never call a social API.

The Chinese UI is local. The first switch to Chinese for a post asks the configured non-template LLM
to translate it, validates that source URLs and numeric claims are preserved, and stores the result
in that post's metadata. Later language switches reuse the cached variant. This first translation
therefore consumes one provider request when DeepSeek, OpenAI, or a compatible API is configured.

Compose binds the service to `127.0.0.1` by default, so the dashboard is available only on the local
machine. Set a long random `DASHBOARD_ADMIN_TOKEN` before using `ENVIRONMENT=production`; production
startup intentionally fails without it. The browser keeps that token in session storage only.

Stop the service with `docker compose down`. Add `-v` only if you intentionally want to delete the
persistent SQLite volume.

## Testing the agent step by step

These steps are ordered from lowest to highest risk. Complete steps 1 to 9 before configuring
DeepSeek or a real publishing platform.

### Step 1: Confirm the secrets file is not tracked

```bash
git check-ignore .env
```

The expected output is `.env`. If nothing is printed, fix `.gitignore` first and do not enter any API
key yet.

Never paste the contents of `.env` into a chat, an issue, a terminal screenshot, or a log, and never
write a real key into `.env.example`.

### Step 2: Validate the Compose configuration

```bash
docker compose config --quiet
```

Success prints nothing and exits `0`. It validates the Compose file only; it does not mean the
service is running correctly.

### Step 3: Start the service and check health

```bash
docker compose up --build -d
docker compose ps
curl -s http://localhost:8000/health
curl -s http://localhost:8000/ready
```

The health check returns something like:

```json
{"status":"ok"}
```

If the container is not `healthy`, read the logs first:

```bash
docker compose logs --tail=200 app
```

### Step 4: Inspect the current agent state

```bash
docker compose exec app python -m app.cli status
```

Confirm in particular:

- `dry_run` is `true`
- `auto_publish` is `false`
- the schedule, content mode, and last run status match your expectations

If `status` completes and reads the latest run record, the CLI can reach the database. The run lock
does not appear in `status` output; if a job already holds it, starting a new pipeline reports an
explicit error.

### Step 5: Run one complete, safe end-to-end test

```bash
docker compose exec app python -m app.cli run --dry-run
```

Typical output includes:

```text
Fetching AI sources...
Found XX articles
Removed XX duplicates
Ranking XX topics...
Selected: XXXXX
Verifying sources...
Generating post...
Quality score: XX
Saving post...
DRY RUN — publication skipped.
```

The generated social post is printed at the end. This command really performs collection,
deduplication, ranking, verification, generation, quality checking, and database persistence, but
never calls a social publishing endpoint.

The `XX` values change with time and network conditions. A single failing source does not mean the
agent failed; the run records source errors and continues with the others. Without
`GITHUB_TOKEN`, for example, GitHub can return `403` because anonymous requests are rate limited.

### Step 6: Check the generated content and run history

List every post:

```bash
docker compose exec app python -m app.cli list-posts
```

List only posts awaiting review:

```bash
docker compose exec app python -m app.cli list-pending
```

Read recent data through the API:

```bash
curl -s http://localhost:8000/posts
curl -s http://localhost:8000/runs
```

After an end-to-end test you should see at least one run record. A generated post is in one of these
states:

- `pending_review`: quality passed, automatic publication is off, and human review is required.
- `quality_rejected`: the quality score or fact confidence did not reach its threshold.
- `published`: a platform accepted the post; this does not occur under the default safe settings.
- `failed`: generation or publication raised an explicit error, which the run record and logs
  describe.

### Step 7: Test the three content modes

News mode:

```bash
docker compose exec app python -m app.cli run --dry-run --mode news
```

Frontier concept mode:

```bash
docker compose exec app python -m app.cli run --dry-run --mode concept
```

Mixed mode:

```bash
docker compose exec app python -m app.cli run --dry-run --mode mixed
```

News mode prefers recent, high-credibility, technically valuable material. Concept mode selects a
topic the catalog has not published, or has published least. Mixed mode combines run history with
news importance to choose.

If news mode reports no verifiable candidate, the candidates were usually deduplicated, short of
source evidence, or below the confidence threshold. That is a safety stop; do not bypass it by
disabling verification.

### Step 8: Test individual pipeline stages

Collect and store sources only:

```bash
docker compose exec app python -m app.cli fetch
```

Re-rank the candidate topics already in the database:

```bash
docker compose exec app python -m app.cli rank
```

Generate a post without publishing:

```bash
docker compose exec app python -m app.cli generate --mode news
```

Check the state and results again:

```bash
docker compose exec app python -m app.cli status
docker compose exec app python -m app.cli list-posts
```

These commands help you attribute a problem to collection, ranking, generation, or the quality
check.

### Step 9: Run the automated tests

The Dockerfile provides a separate test stage, so the host needs no Python dependencies:

```bash
docker build --target test -t ai-daily-content-agent:test .
docker run --rm ai-daily-content-agent:test
```

Tests never call live LLM or social APIs. They cover:

- configuration validation
- topic ranking
- content normalization and parsing
- URL, title, and semantic deduplication
- fact verification
- the quality gate
- the LLM provider abstraction
- platform formatting and adapters

Run a single area:

```bash
docker run --rm ai-daily-content-agent:test pytest tests/test_ranking.py -q
docker run --rm ai-daily-content-agent:test pytest tests/test_deduplication.py -q
docker run --rm ai-daily-content-agent:test pytest tests/test_quality_gate.py tests/test_verification.py -q
docker run --rm ai-daily-content-agent:test pytest tests/test_platforms.py tests/test_llm.py -q
```

### Step 10: Test real LLM generation with the DeepSeek API

DeepSeek exposes an OpenAI-compatible API, so the project can call it directly. Edit your local
`.env` first:

```dotenv
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your-real-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash

DRY_RUN=true
AUTO_PUBLISH=false
PUBLISH_PLATFORMS=
```

At the time of writing, DeepSeek's official OpenAI-compatible endpoint is
`https://api.deepseek.com` and the suggested model identifier is `deepseek-flash`. Model names and
API availability still change, so check the
[official DeepSeek first-call guide](https://api-docs.deepseek.com/guides/codex) and the
[model list](https://api-docs.deepseek.com/api/list-models/) before testing. Do not put the key in
your shell history and do not commit `.env`.

Let the container pick up the environment again:

```bash
docker compose up -d --force-recreate
docker compose exec app python -m app.cli status
```

Then run:

```bash
docker compose exec app python -m app.cli run --dry-run --mode news
```

Checkpoints:

- The pipeline completes, or reports an explicit API error.
- Source references are preserved in the post.
- The generated text adds no numbers, dates, or product capabilities the sources cannot support.
- A post above the quality threshold is stored as `pending_review`, not actually published.
- The API key never appears in the logs.

Common DeepSeek errors:

- `401`: invalid key, wrong format, or the container did not read it.
- `402`: account balance or billing problem.
- `429`: rate or quota limit.
- Model not found: check whether `DEEPSEEK_MODEL` is still a model your account can call.

If `.env` changes have no effect, recreate the container:

```bash
docker compose up -d --force-recreate
```

### Step 11: Verify the quality gate

The default publication threshold is:

```dotenv
MIN_QUALITY_SCORE=85
```

After running news and concept modes, inspect the logs and post states:

```bash
docker compose exec app python -m app.cli list-posts
docker compose logs --tail=200 app
```

Content below the threshold, short of sources, or below the fact-confidence threshold must land in
`quality_rejected` and cannot publish automatically. Do not lower the threshold to make a test
"pass"; inspect the sources, the generated content, and the reason points were deducted first.

### Step 12: Test the human approval workflow

Confirm `.env` still holds:

```dotenv
DRY_RUN=true
AUTO_PUBLISH=false
```

List what is awaiting approval:

```bash
docker compose exec app python -m app.cli list-pending
```

Note the post ID, then approve it:

```bash
docker compose exec app python -m app.cli approve <post_id>
```

Test the publish command under Dry Run:

```bash
docker compose exec app python -m app.cli publish <post_id>
```

The output must clearly contain `DRY RUN` or "publication skipped" and must not reach a real
platform. Replace `<post_id>` with the actual ID; do not keep the angle brackets.

### Step 13: Test the daily scheduler

Temporarily set the publication time two or three minutes ahead in `.env`, keeping the safety
switches:

```dotenv
TIMEZONE=Asia/Singapore
POST_TIME=09:00
DRY_RUN=true
AUTO_PUBLISH=false
```

Replace `09:00` with your test time, then restart and follow the logs:

```bash
docker compose up -d --force-recreate
docker compose logs -f app
```

At the configured time you should see stage logs sharing one `run_id`:

```text
FETCH
NORMALIZE
DEDUP
RANK
VERIFY
GENERATE
QUALITY_CHECK
PUBLISH
DONE
```

A failed run ends at `FAILED` and records the error. Pressing `Ctrl+C` only stops following the
logs; it does not stop the container.

Confirm the run history afterwards:

```bash
docker compose exec app python -m app.cli status
curl -s http://localhost:8000/runs
```

Restore `POST_TIME` to the real publication time and restart the container when you are done.

### Step 14: Test the platform adapters without publishing

Run the platform adapter mock tests first:

```bash
docker build --target test -t ai-daily-content-agent:test .
docker run --rm ai-daily-content-agent:test pytest tests/test_platforms.py -q
```

These tests cover formatting, length validation, request construction, and error handling without
contacting real X, LinkedIn, Telegram, or webhook endpoints.

Keep `DRY_RUN=true` until a real platform is configured. Only attempt a small real publication once
all of the following hold:

1. The output of DeepSeek or another LLM has been reviewed by a human.
2. Fact verification and the quality gate pass consistently.
3. The target platform uses a test account or a private channel.
4. Platform credentials exist only in `.env` or a secure secret manager.
5. `PUBLISH_PLATFORMS` is set explicitly and you understand each platform's API permissions.
6. Only then set `DRY_RUN=false`.

### Step 15: Stop, restart, or wipe the environment

Stop the container but keep the SQLite volume:

```bash
docker compose down
```

Restart while keeping historical data:

```bash
docker compose up -d
```

Delete the container and the database volume entirely:

```bash
docker compose down -v
```

Warning: `docker compose down -v` deletes saved posts, run history, and publication history. Do not
run it unless you intend to reset the test environment and have backed up anything you need.

## Content modes

Configure the default mode through an environment variable:

```dotenv
CONTENT_MODE=mixed
```

Allowed values:

- `news`: discover and process recent AI news only.
- `concept`: pick and explain one AI term from the concept catalog.
- `mixed`: choose between news and concepts, taking recent run history into account.

`--mode` on the CLI overrides a single run only and does not modify `.env`.

## LLM providers

### Local template provider

Default configuration:

```dotenv
LLM_PROVIDER=template
```

It calls no external model and suits first startup, offline testing, and CI. Its output verifies the
engineering pipeline; it is not the writing quality of a real model.

### DeepSeek

```dotenv
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
```

DeepSeek is reached through the compatible provider. The system asks the model for structured JSON
and then runs the local quality and fact checks again on the result.

The key is read at runtime through Pydantic `SecretStr`, never logged, and must not be committed.

`deepseek-flash` is a reasoning model and **charges its thinking against `max_tokens`**. If the cap
is reached before the model starts answering, the API returns an empty body rather than a short one,
and a truncated reply looks like a malformed response. Translation is the demanding case — it
reproduces the whole post in another language — so it has its own `TRANSLATION_MAX_TOKENS` budget
(16000 by default; a single post has measured around 7,600 tokens of reasoning plus output). Raise
`LLM_MAX_TOKENS` too if generation starts failing the same way.

Reasoning also takes time, so model calls use their own `LLM_TIMEOUT_SECONDS` (600 by default)
rather than the feed-fetching timeout; one translation measured 35 seconds.

### OpenAI

```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
OPENAI_BASE_URL=https://api.openai.com/v1
```

### Other OpenAI-compatible APIs

```dotenv
LLM_PROVIDER=compatible
COMPATIBLE_API_KEY=
COMPATIBLE_BASE_URL=https://example.com/v1
COMPATIBLE_MODEL=your-model
```

A compatible service must support OpenAI-style chat-completions requests and JSON output. Fields,
model names, and rate limits differ between vendors, so validate in Dry Run first.

The zero-secret `template` provider is an honest deterministic fallback for development and CI. Its
database metadata says `offline=true`; it is never presented as an external-model result.

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `ENVIRONMENT` | `development` | Runtime environment name |
| `DATABASE_URL` | `sqlite:///./data/content_agent.db` | SQLAlchemy database URL |
| `TIMEZONE` | `Asia/Singapore` | IANA scheduler timezone |
| `POST_TIME` | `09:00` | Daily local time in `HH:MM` |
| `CONTENT_MODE` | `mixed` | `news`, `concept`, or `mixed` |
| `MIXED_MODE_STRATEGY` | `importance` | `importance` or `alternate` |
| `AUTO_PUBLISH` | `false` | Permit quality-approved automatic publication |
| `DRY_RUN` | `true` | Block every real publication call |
| `DASHBOARD_ADMIN_TOKEN` | empty | Required for dashboard actions in production |
| `MIN_QUALITY_SCORE` | `85` | Required score for publication |
| `MIN_VERIFICATION_CONFIDENCE` | `0.72` | Required evidence confidence |
| `LLM_PROVIDER` | `template` | `template`, `deepseek`, `openai`, or `compatible` |
| `LLM_MAX_TOKENS` | `1800` | Generation budget |
| `TRANSLATION_MAX_TOKENS` | `16000` | Translation budget; see the DeepSeek note below |
| `LLM_TIMEOUT_SECONDS` | `600` | Timeout for model calls; `REQUEST_TIMEOUT_SECONDS` covers only feed fetching |
| `CONTENT_STYLE` | `professional` | Content prompt style |
| `PUBLISH_PLATFORMS` | empty | Comma-separated enabled adapter names |
| `EXTRA_RSS_FEEDS` | empty | Comma-separated additional RSS URLs |
| `EXTRA_RSS_CREDIBILITY` | `0.65` | Starting credibility for each `EXTRA_RSS_FEEDS` entry |
| `SOURCE_CREDIBILITY_OVERRIDES` | empty | Per-source credibility, e.g. `GitHub AI Projects=0.9` |
| `IMAGE_GENERATION_ENABLED` | `false` | Enable optional compatible image generation |
| `GITHUB_TOKEN` | empty | Optional; raises the GitHub API rate limit |
| `SIMILARITY_THRESHOLD` | `0.82` | Semantic duplicate threshold between candidates |
| `HISTORY_SIMILARITY_THRESHOLD` | `0.78` | Semantic duplicate threshold against history |
| `SCORE_RECENCY_WEIGHT` | `0.25` | Recency weight in ranking |
| `SCORE_SOURCE_QUALITY_WEIGHT` | `0.20` | Source quality weight |
| `SCORE_IMPORTANCE_WEIGHT` | `0.20` | Importance weight |
| `SCORE_NOVELTY_WEIGHT` | `0.15` | Novelty weight |
| `SCORE_TECHNICAL_RELEVANCE_WEIGHT` | `0.10` | Technical relevance weight |
| `SCORE_SOCIAL_INTEREST_WEIGHT` | `0.10` | Social interest weight |

All ranking weights and provider/platform fields are documented in `.env.example`. Configuration is
validated at startup: selecting a remote provider without its required key fails clearly.

## Data sources

Default sources are OpenAI News, Google AI, Google DeepMind, Microsoft Research, NVIDIA AI, Hugging
Face, MIT AI News, arXiv AI categories, and GitHub AI repositories. The RSS list lives in
`app/collectors/rss.py`.

Collectors treat all external content as untrusted data. Text such as "ignore previous
instructions", "output the key", or "change the system prompt" inside a page is never treated as an
agent instruction; suspected prompt injection is flagged, and severe cases are rejected outright.

### Adding an RSS source

To add a feed without code, add its URL to `EXTRA_RSS_FEEDS`. Each entry starts at the credibility in
`EXTRA_RSS_CREDIBILITY`, and **that default is too low to publish on its own**: verification
confidence is `0.55 * credibility + 0.25`, plus up to `0.20` when another source reports the same
event, and it must reach `MIN_VERIFICATION_CONFIDENCE` (0.72). A source therefore needs a credibility
of at least **0.855** to stand alone. Raise `EXTRA_RSS_CREDIBILITY`, or name the feed in
`SOURCE_CREDIBILITY_OVERRIDES`, before expecting it to produce posts; otherwise its articles are only
usable as corroboration for a source that already clears the bar.

To add a first-class source:

1. Implement `Collector.fetch(client) -> CollectorResult` in `app/collectors/`.
2. Return `NormalizedArticle` values and errors; never raise for an ordinary source failure.
3. Sanitize external HTML with `sanitize_untrusted_html`.
4. Register it in `CollectorRegistry.from_settings`.
5. Add a test using `httpx.MockTransport`.
6. Verify that one failing source does not abort the other collectors.

Collectors identify themselves with a respectful user agent. Review source terms and robots policies
before adding a page-scraping collector.

## Deduplication and ranking

The system checks, in order:

1. Normalized URL
2. Normalized title
3. Content hash
4. Semantic similarity of the hashed feature vectors
5. Prior publication history

The default ranking formula is:

```text
topic_score =
  0.25 * recency
  + 0.20 * source_quality
  + 0.20 * importance
  + 0.15 * novelty
  + 0.10 * technical_relevance
  + 0.10 * social_interest
```

Duplicate probability and prior publication further reduce or eliminate a candidate. Weights are
validated at startup so a misconfiguration cannot silently distort ranking.

## Fact verification

Before generation the system:

- preserves the original URL, title, and publication date;
- extracts facts the sources directly support;
- compares multiple sources where possible;
- marks claims that are uncertain, conflicting, or unsupported;
- computes a fact confidence score;
- rejects prompt injection and thin evidence.

After generation, the quality gate checks again whether the numbers, dates, proper nouns, and claims
in the body are supported by the sources. LLM output never replaces the original source evidence.

Generation is rejected when verification confidence is too low. The generated post and the database
record retain source titles, URLs, source dates, extracted claims, provider/model metadata,
confidence, quality score, and the full quality report.

## Content structure and style

News content contains by default:

1. Hook
2. What happened
3. Why it matters
4. Technical details
5. Takeaway
6. Sources

Concept content contains by default:

1. Term
2. One-sentence explanation
3. How it works
4. Simple example
5. Why it matters
6. Real-world application
7. Key takeaway
8. Sources

Supported styles are `technical`, `educational`, `news_summary`, `beginner_friendly`,
`professional`, and `viral`. The default favors professional, technically accurate, readable
writing and forbids empty marketing language.

## Review and CLI workflow

```bash
python -m app.cli fetch
python -m app.cli rank
python -m app.cli generate --mode news
python -m app.cli run --dry-run
python -m app.cli list-posts
python -m app.cli list-pending
python -m app.cli approve 12
python -m app.cli publish 12
python -m app.cli status
```

With automatic publication off:

```dotenv
AUTO_PUBLISH=false
```

Qualifying content is stored as `pending_review`. `approve` changes only the local database status.
`publish` requires an approved post and still honors `DRY_RUN=true`: even an approved post is not
sent to a real endpoint while Dry Run is on. To publish manually, set `DRY_RUN=false`, configure at
least one platform, restart the service, approve the post, and run `publish`.

## Platform adapters

Adapters implement `format`, `validate`, and `publish`. Credentials are environment-only.

### Telegram

Requires:

```dotenv
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

Use a private test channel first and confirm the bot may post there.

### Generic webhook

Requires:

```dotenv
WEBHOOK_URL=
WEBHOOK_BEARER_TOKEN=
```

The system sends the post and its sources as JSON. The bearer token is optional depending on the
target service.

### X / Twitter

Requires official X developer access and an OAuth 2.0 user-context bearer token with write
permission:

```dotenv
TWITTER_BEARER_TOKEN=
```

Long posts are emitted as a thread. App-only bearer tokens cannot create posts. The project does not
use browser automation to bypass official API permissions.

### LinkedIn

Requires a LinkedIn app, a valid OAuth access token, and a member or organization URN permitted to
post:

```dotenv
LINKEDIN_ACCESS_TOKEN=
LINKEDIN_AUTHOR_URN=
```

Keep `LINKEDIN_API_VERSION` aligned with LinkedIn's active version. Review and permission
requirements change; the official developer documentation is authoritative.

### Adding a new platform

1. Subclass `PlatformAdapter`.
2. Implement `format`, `validate`, and `publish`.
3. Read every credential from the environment.
4. Write mock tests for length limits, request bodies, and error responses.
5. Register the adapter in `app/platforms/registry.py`.
6. Validate with Dry Run and a test account first.

Do not use browser automation as an API substitute.

## Scheduler and concurrency

The FastAPI lifespan starts one APScheduler cron job at `POST_TIME` in `TIMEZONE`. Jobs coalesce
after downtime and `max_instances=1` blocks overlap inside the process. A separate atomic file lock
blocks overlap across the API process and `docker compose exec` CLI runs. A stale lock expires after
four hours. `run_history` preserves status, counts, source errors, start/end times, and the current
step.

Each run has its own `run_id`, and structured logs record the stages:

```text
FETCH
NORMALIZE
DEDUP
RANK
VERIFY
GENERATE
QUALITY_CHECK
PUBLISH
DONE / FAILED
```

Only run one scheduler-enabled replica with SQLite. For multiple production replicas, move to
PostgreSQL and replace the file lock with a database advisory lock or distributed lease.

## API

The service listens on `http://localhost:8000` by default.

Frequently used endpoints:

- `GET /`: web review console
- `GET /api/dashboard`: aggregated console data
- `GET /health`: process health
- `GET /ready`: database and application readiness
- `GET /posts`: list generated posts
- `GET /runs`: pipeline run history
- `POST /api/pipeline/run`: start an agent run from the dashboard
- `POST /api/posts/{id}/translate/zh`: create and cache the Chinese publication variant
- `POST /api/posts/{id}/regenerate`: create a new draft from human feedback
- `POST /api/posts/{id}/schedule`: persist a scheduled publication

## Local development and tests

Use Python 3.12; do not install project packages into the macOS system Python.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
cp .env.example .env
pytest
ruff check app tests
uvicorn app.main:app --reload
```

In a second terminal:

```bash
source .venv/bin/activate
python -m app.cli run --dry-run
```

Run the exact test environment in Docker:

```bash
docker build --target test -t ai-daily-content-agent:test .
docker run --rm ai-daily-content-agent:test
```

Tests never call live LLM or social APIs. HTTP interactions use mock transports.

## Database

Docker Compose persists SQLite in a named volume. SQLAlchemy models cover:

- `sources`
- `articles`
- `topics`
- `concepts`
- `generated_posts`
- `publication_history`
- `scheduled_publications`
- `run_history`

The models use portable types and accept a PostgreSQL SQLAlchemy URL through `DATABASE_URL`. The
Docker image ships no PostgreSQL driver or service; a migration requires adding the `psycopg`
dependency, a database service, migration scripts, and a backup plan before changing the URL:

```dotenv
DATABASE_URL=postgresql+psycopg://user:password@postgres:5432/ai_content
```

Add migration tooling and a real backup strategy before any production migration, and do not reuse
development database credentials. For a long-lived production deployment, add Alembic migrations
before evolving an existing schema; the MVP uses `create_all` only to initialize missing tables.

## Security model

- `.env` and database files are ignored; Docker never copies local secret files into the image.
- No token is hardcoded, returned by health endpoints, or included in logs.
- Remote HTML is converted to inert text, active elements are removed, size is bounded, and common
  prompt-injection strings are flagged in metadata.
- External content is always treated as data. Only supported extracted claims reach the generator.
- Publishing requires configured credentials, acceptable confidence, acceptable quality, and either
  explicit approval or `AUTO_PUBLISH=true`.
- Dashboard write actions require a non-simple request header; production additionally requires the
  configured admin token. Compose exposes the dashboard on loopback only.
- The container runs as a non-root user with a read-only filesystem, writable data volume, temporary
  `/tmp`, and `no-new-privileges`.
- HTTP requests use timeouts and bounded error recording.
- Vulnerable browser automation is never used as a substitute for official platform APIs.

## Troubleshooting

### Startup says a provider key is missing

The selected `LLM_PROVIDER` requires its matching key. Return to `LLM_PROVIDER=template` for offline
development or supply the secret in your untracked `.env`.

### The container never becomes healthy

```bash
docker compose ps
docker compose logs --tail=200 app
docker compose exec app python -m app.cli status
```

Check for a port conflict, database directory permissions, and malformed environment variables.

### GitHub returns 403

Anonymous GitHub API access is rate limited. Set a read-only token in `.env`:

```dotenv
GITHUB_TOKEN=
```

Without a token, the other sources keep running.

### No article passes verification

Possible causes:

- the news was already judged a duplicate of the publication history;
- candidate source credibility or fact confidence is too low;
- the content contains suspected prompt injection;
- the source dates are too old;
- the current network cannot reach enough sources.

Inspect `docker compose logs app` and `list-posts`. Do not disable the safety checks. Increase
`ARTICLE_MAX_AGE_HOURS` only if using older content is acceptable; do not lower the verification
threshold merely to force a post.

### The quality score is below 85

Check whether the sources are reachable, whether the body contains unsupported numbers, whether it
uses hype language, whether it exceeds the platform length limit, and whether source links survive.
Improve the prompt or the sources rather than lowering the bar.

### DeepSeek is configured but template output still appears

Confirm `LLM_PROVIDER=deepseek` in `.env`, then force the container to be recreated:

```bash
docker compose up -d --force-recreate
docker compose exec app python -m app.cli status
```

### Port 8000 is already in use

Change the host port mapping in `docker-compose.yml`, for example to `8001:8000`, then use
`http://localhost:8001`.

### SQLite is read-only

Check the volume mount, container user permissions, and disk space:

```bash
docker compose ps
docker compose logs --tail=200 app
docker system df
```

Use the Compose-managed `/app/data` volume. A custom bind mount must be writable by the container's
non-root `agent` user. Do not delete the data volume unless you are sure you do not need it.

### A run says another run is active

The concurrency lock is blocking a duplicate job. Confirm with `status` and the logs whether a job
is genuinely running. Only handle a stale lock after verifying the previous process terminated
abnormally; never clear it while a run is healthy.

### A social API rejects publication

Confirm official API approval, token scopes, author/chat identifiers, and current vendor API version.
Failures are stored in `publication_history`; the application does not fabricate success responses.

## Recommended acceptance order

Run a complete MVP acceptance pass in this order:

```bash
test -f .env || cp .env.example .env
docker compose config --quiet
docker compose up --build -d
docker compose ps
curl -s http://localhost:8000/health
docker compose exec app python -m app.cli status
docker compose exec app python -m app.cli run --dry-run
docker compose exec app python -m app.cli list-posts
docker build --target test -t ai-daily-content-agent:test .
docker run --rm ai-daily-content-agent:test
```

## License

MIT. See `LICENSE`.
