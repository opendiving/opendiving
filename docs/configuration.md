# Configuration reference

Everything is configured through one `.env` file next to `docker-compose.yml`. The compose file
feeds it to the API and the worker wholesale, and hands the web container only the handful of
variables it needs — so database and SMTP credentials never enter the Node process at all.

An edit to `.env` takes effect on `docker compose up -d`, which recreates what changed. A plain
`docker compose restart` does **not** re-read the file: it restarts the process inside a container
that keeps the environment it was created with.

The API has more settings than are listed here — token lifetimes, every rate limit, the geocoder and
species providers. [`src/.env.example`](https://github.com/opendiving/opendiving-api/blob/main/src/.env.example) in `opendiving-api` is the
full annotated list and [`src/app/core/config.py`](https://github.com/opendiving/opendiving-api/blob/main/src/app/core/config.py)
is the authority; the groups below say which of them a
self-hoster normally touches, and any setting from that file can be added to `.env` verbatim.

## The six that matter

| Variable                         | Default             | What it does                                                                                                    |
| -------------------------------- | ------------------- | --------------------------------------------------------------------------------------------------------------- |
| `DOMAIN`                         | *(none — required)* | The hostname this instance answers on. Drives the certificate, the emailed links and the web app's own origin.  |
| `SECRET_KEY`                     | *(none — required)* | Signs every token the API issues. `openssl rand -hex 32`. Startup **fails** on the published placeholder value. |
| `POSTGRES_PASSWORD`              | *(none — required)* | The database password, read once when the volume is first created.                                              |
| `SMTP_HOST`, `SMTP_PORT`         | *(none)*            | The mail relay. Required on any `ENVIRONMENT` but `local`, because sign-in is passwordless.                     |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | *(none)*            | Its credentials. Both optional and independent — a relay that authenticates by IP needs neither.                |
| `EMAIL_FROM_ADDRESS`             | *(none)*            | The address mail is sent as. Required as soon as `SMTP_HOST` is set; startup fails without it.                  |

## Serving

| Variable             | Default             | What it does                                                                                                                                                                                |
| -------------------- | ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `COMPOSE_PROFILES`   | `proxy`             | Runs the bundled Caddy. Comment it out to bring your own proxy — [reverse-proxy.md](reverse-proxy.md).                                                                                      |
| `CADDY_SITE_ADDRESS` | `${DOMAIN}`         | The address Caddy answers on. `:80` for a LAN instance with no certificate.                                                                                                                 |
| `TRUSTED_PROXY_IPS`  | `172.29.0.0/16`     | Whose `X-Forwarded-For` and `X-Forwarded-Proto` the API believes. Every per-IP rate limit depends on it, as do the admin panel's HTTPS enforcement and its IP allowlist.                    |
| `ENVIRONMENT`        | `production`        | `production` hides `/docs`. `staging` puts them behind a superuser; both require `SMTP_HOST`. `local` opens the docs and logs sign-in links instead of emailing them.                       |
| `FRONTEND_URL`       | `https://${DOMAIN}` | Where emailed links point, the API's single allowed CORS origin, and the passkey domain — see [Sign-in](#sign-in) before changing its hostname. Override for a plain-HTTP instance.         |
| `SITE_URL`           | `https://${DOMAIN}` | The web app's own origin, used for link previews. Override alongside `FRONTEND_URL`.                                                                                                        |
| `AUTH_COOKIE_SECURE` | `true`              | The refresh cookie's `Secure` flag. `false` only for plain HTTP, where the browser otherwise drops it and every reload signs the user out.                                                  |
| `WEB_HSTS`           | `on`                | `Strict-Transport-Security`, sent only on requests that already arrived over HTTPS. `off` hands the header to a proxy in front, or supports an instance that must stay reachable over HTTP. |
| `WEB_NOINDEX`        | `off`               | `true` disallows all crawlers and adds `X-Robots-Tag: noindex, nofollow` to every page.                                                                                                     |
| `OPENDIVING_VERSION` | `latest`            | The image tag both containers run. Pin it once this instance holds dives you'd miss.                                                                                                        |
| `LOG_LEVEL`          | `INFO`              | Applied to the API and the worker alike.                                                                                                                                                    |

## Who may create an account

New installs are **invite-only**. That is the default and it is a deliberate one: an instance
reachable from the internet with nothing configured would otherwise take anybody who found it, and
this one holds people's dive logs. Set `REGISTRATION_MODE=open` if you want the other behaviour,
which is what this app did before the setting existed.

| Variable                                   | Default  | What it does                                                                                                                                                                                                                                                                                                       |
| ------------------------------------------ | -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `REGISTRATION_MODE`                        | `invite` | `invite` admits only an address somebody already invited: the home page offers a stranger a **Request an invite** form instead of a sign-in form, and their address joins a queue you work through. `open` gives an account to anybody who proves they own an address. The first account on an empty instance needs no invitation in either mode — see below. An unknown value refuses to start. |
| `INVITATIONS_PER_USER`                     | `5`      | How many invitations one member may send per window. A rate, not a lifetime allotment. Counted from the invitations themselves, revoked ones included, so it bounds emails sent. Superusers are exempt.                                                                                                            |
| `INVITATIONS_WINDOW_DAYS`                  | `1`      | The window those are counted over.                                                                                                                                                                                                                                                                                 |
| `INVITATION_ATTEMPT_RATE_LIMIT_PER_USER`   | `20`     | A separate backstop on how often one member may *attempt* an invitation, over `MAGIC_LINK_RATE_LIMIT_WINDOW_SECONDS`. Inviting an address that already has an account is refused without creating anything, so the quota above never charges for it; this is what stops that refusal being a probe. Superusers get it too. |
| `INVITE_REQUEST_RATE_LIMIT_WINDOW_SECONDS` | `3600`   | The window for the two limits below, on the anonymous request-an-invite endpoint. Consulted only in `invite` mode.                                                                                                                                                                                                 |
| `INVITE_REQUEST_RATE_LIMIT_PER_EMAIL`      | `3`      | Requests per window for one submitted address.                                                                                                                                                                                                                                                                     |
| `INVITE_REQUEST_RATE_LIMIT_PER_IP`         | `10`     | Requests per window from one caller, subject to `TRUSTED_PROXY_IPS` being right.                                                                                                                                                                                                                                   |

**The first account to sign in is yours, in both modes.** While the `user` table is empty the gate
lets the address through whatever `REGISTRATION_MODE` says, and the account it creates carries the
operator's rights. That is what keeps closed-by-default from being a first-run trap — a fresh
instance has no invitations and nobody who could send one — and it is why nothing here needs SQL or
a bootstrap script. It fires on the table being empty rather than once, so an instance whose last
account is deleted and purged hands the same deal to whoever signs in next.

**How you invite people.** Every member has an *Invitations* card in Settings, subject to the quota
above. As the operator you also get an **Admin** entry in the account menu — sign in as the first
account, open the menu, choose *Admin* — which lists the queue of addresses that used the request
form, tells you which of them already have an account, and invites or removes them in a batch. An
invitation is an entry against the email address rather than a code to forward: the invitee signs in
with the address that was invited — by link, code or Google, exactly as anybody else does — so there
is no token for them to lose and nothing extra for you to explain.

Somebody who is not invited still gets their sign-in email. The endpoint that sends it deliberately
never learns whether an address is invited, or even whether it has an account, which is what keeps
it from being a way to enumerate your users; the refusal comes afterwards, once the link or code has
proven the address is theirs. [Troubleshooting](troubleshooting.md) has the message they see.

Requests that nobody acts on are deleted after 90 days, and so is an invitation nobody accepts; both
are somebody else's email address sitting in your database, and neither is a setting.

Flipping the mode is a restart of the `api` container with the new `.env` applied — `docker compose
up -d`, as with every setting here. The web app asks the API which mode it is in, so there is
nothing to change on the `web` service and nothing to redownload.

## Sign-in

Sign-in is passwordless, and an instance offers up to three ways in. **Email always works**: the
sign-in mail carries a link *and* a six-digit code, either of which completes it — the code is there
for the ordinary case of typing your address on a laptop and reading the mail on a phone. **Google**
appears if you set `GOOGLE_CLIENT_ID`. **Passkeys** appear when the visitor's browser can do
WebAuthn against this instance, which is a property of how you deployed it rather than a setting —
see below.

Nothing here is required. The defaults are the tested configuration, and an instance that sets none
of it still has working sign-in as long as mail is delivered. Who is *allowed* to end up with an
account is the separate question above — [Who may create an account](#who-may-create-an-account) —
and the answer to it changes none of the three methods.

| Variable                               | Default | What it does                                                                                                                                                                                    |
| -------------------------------------- | ------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `SIGN_IN_CODE_ATTEMPTS_MAX`            | `5`     | Wrong guesses allowed against the emailed code. Running out spends the code only — the link in the same mail still works.                                                                       |
| `PASSKEY_CHALLENGE_TTL_SECONDS`        | `600`   | How long a started ceremony stays completable. It is spent on the first attempt either way, so this bounds only an abandoned one.                                                               |
| `PASSKEY_MAX_CREDENTIALS_PER_USER`     | `10`    | Passkeys one account may hold. Abuse hygiene, not product policy.                                                                                                                               |
| `PASSKEY_OPTIONS_RATE_LIMIT_PER_IP`    | `240`   | Per IP, per `MAGIC_LINK_RATE_LIMIT_WINDOW_SECONDS`. High because one is minted per signed-out page view that offers passkey autofill, and an office behind one NAT gateway is a single IP here. |
| `PASSKEY_VERIFY_RATE_LIMIT_PER_IP`     | `30`    | Per IP, same window.                                                                                                                                                                            |
| `PASSKEY_REGISTER_RATE_LIMIT_PER_USER` | `10`    | Per signed-in account, same window.                                                                                                                                                             |
| `REFRESH_TOKEN_EXPIRE_DAYS`            | `7`     | How long a browser stays signed in **without the app being used**. A rolling window, not a session length — read below before changing it.                                                      |

**Two things worth knowing before you change the number.** The refresh cookie is single-use: each
time it is spent a fresh one replaces it with the clock started again, so this setting bounds
*inactivity* rather than the session. A browser used every day stays signed in indefinitely; one
left alone for longer than this asks for a sign-in link again. That is the behaviour the web app
describes, so raising or lowering it changes what the app does rather than only how long a token
lives.

And the number is quoted back to divers in two places the web image ships as prose — the note under
the sign-in button and the bundled privacy page's section on the sign-in cookie, both of which say
"about a week" from the default of 7. Neither reads this setting, so an instance that changes it has
two lines of copy that no longer match it. It is the same coupling as the privacy page's "within 30
days" against [account deletion](#account-deletion), and the same remedy: pick a number your own
copy can honestly stand behind, or expect to edit those two lines.

There is deliberately **no on/off switch for passkeys**. The browser's own capability detection is
the switch: where a ceremony cannot work the web app hides the option rather than offering one that
fails, and a server flag would only be a second place for the answer to be wrong.

### Passkeys need HTTPS, and a hostname

Browsers expose WebAuthn only in a secure context, and they scope a credential to a *domain*. So an
instance is eligible when it is reached over HTTPS at a **hostname**:

- **Plain HTTP** gets no WebAuthn at all. The passkey option simply never appears; the emailed link
  and code serve that instance fully. This is the `AUTH_COOKIE_SECURE=false` LAN shape in
  [reverse-proxy.md](reverse-proxy.md) — nothing about it is broken, it just has two methods instead
  of three.
- **An IP address is never eligible**, certificate or not. `https://192.168.1.10` is a secure
  context, so the browser offers the API and then fails every ceremony: an IP is not a valid
  relying-party id. A hostname is the fix, not a better certificate.
- **`localhost` is exempt** by specification, which is why passkeys work in local development over
  plain HTTP.

The bundled Caddy gets a certificate for `DOMAIN` on its own, so the default install is already
eligible. A LAN box can become eligible without going public: anything that gives it a real hostname
and a certificate the browser trusts — a Tailscale HTTPS name, an internal CA — works, as long as
`FRONTEND_URL` is then set to that `https://` hostname.

### `FRONTEND_URL` is the passkey domain

The relying-party id and the expected origin are both derived from it; there is no separate setting.
Two consequences worth knowing before you edit it:

- **Changing its hostname orphans every passkey already registered.** Browsers will not offer a
  credential created under one domain to another, and the API will not accept one. Nobody is locked
  out — the emailed link is the recovery path, and everyone re-adds a passkey afterwards — but it is
  silent, so treat a hostname change as "everyone signs in by email once".
- **Write it without a trailing slash.** The origin is rebuilt from the parsed URL rather than
  concatenated, so `https://dive.example.com/` is tolerated — but keep it clean anyway, since the
  same value is compared against what the browser sends.

`SITE_URL` is the web app's own origin and should move with it.

### Setting up Google sign-in

Google sign-in needs an OAuth client of your own, created once in the
[Google Cloud Console](https://console.cloud.google.com/apis/credentials). It is the only optional
feature here that requires anything outside this instance, and there is no shared or default client
to fall back on — an OAuth client is tied to the exact URLs it will redirect to, so it has to be
yours.

Create credentials of type **OAuth client ID**, application type **Web application**. Two things
come out of it and both go in your `.env`:

| From the Console  | Into `.env`            | Secret?                                                                                           |
| ----------------- | ---------------------- | ------------------------------------------------------------------------------------------------- |
| **Client ID**     | `GOOGLE_CLIENT_ID`     | No. It travels in a URL the visitor can read, and the web app uses it too.                        |
| **Client secret** | `GOOGLE_CLIENT_SECRET` | **Yes.** It stays on the API. Never put it anywhere the browser or the `web` container can reach. |

Then register, on that same client:

- **Authorized redirect URI** — `{FRONTEND_URL}/auth/google/callback`, exactly. For the default
  install that is `https://dive.example.com/auth/google/callback`; locally it is
  `http://localhost:3000/auth/google/callback`. This is where Google sends the visitor back.

**Upgrading an instance that already had Google sign-in?** That client almost certainly has no
redirect URI at all — the previous flow never sent one, so a client created for it carries an
authorized JavaScript *origin* and nothing else, and the gap is invisible until the first sign-in
attempt after the upgrade. Add the redirect URI above. The origin already on it does no harm and can
stay.

Google constrains both lists the same way, and has done all along — this is not a new restriction,
only one that was never written down here:

- **Redirect URIs must use HTTPS**, with `http://localhost` URIs exempt.
- **The host cannot be a raw IP address**, with localhost IPs exempt.

So a plain-HTTP instance on a LAN address has never been able to offer Google sign-in and still
cannot: there is no redirect URI Google will accept for it. That instance has the emailed link and
code, which serve it fully. It is the same eligibility question passkeys have, for a different
reason, and the same fix — a real hostname and a certificate the browser trusts.

Three separate things can be wrong here, and each says so differently:

- **`GOOGLE_CLIENT_ID` set with no `GOOGLE_CLIENT_SECRET`** — the API refuses to start, naming both
  variables. It fails at startup rather than at the first click because the web app decides whether
  to show the button from its own copy of the client id and cannot know the API is short a secret.
- **`FRONTEND_URL` disagreeing with the origin visitors actually reach** — `POST /auth/google`
  answers 400 naming `FRONTEND_URL`, from this app.
- **A redirect URI you have not registered** — Google refuses the exchange and sign-in answers 401.
  Set `LOG_LEVEL=DEBUG` and the API logs the short reason Google gave (`redirect_uri_mismatch`,
  `invalid_client`, …). Nothing from Google's answer is logged above that level, deliberately.

### When something is down

The three methods fail independently, which is most of the argument for having three:

| Down       | Email link / code    | Passkey                    | Google |
| ---------- | -------------------- | -------------------------- | ------ |
| Mail relay | ✗                    | ✓                          | ✓      |
| Redis      | ✓ (limits fail open) | ✗ (challenges fail closed) | ✓      |
| Google     | ✓                    | ✓                          | ✗      |
| Postgres   | ✗                    | ✗                          | ✗      |

Redis is deliberately the odd one out. Rate limiting there fails *open* — an outage must not lock
everyone out of an app — but a passkey challenge **is** the replay protection, so with Redis
unreachable the passkey endpoints answer 503 rather than verifying a ceremony without one. Email
sign-in is pure Postgres and is unaffected.

The `Google` row covers two different reachability problems, and only one of them is the visitor's.
Their browser has to reach `accounts.google.com` to sign in at all, and **your API has to reach
`oauth2.googleapis.com`** to redeem the code they come back with. So an instance with filtered
outbound traffic can have Google sign-in fail on a network that looks perfectly healthy from the
diver's side, with a 503 rather than a rejected credential. The other two methods are unaffected,
which is the row as drawn.

## Database, cache, migrations

`POSTGRES_SERVER`, `POSTGRES_PORT`, `REDIS_CACHE_HOST` and `REDIS_QUEUE_HOST` are set by the compose
file to the service names and are not yours to change. `POSTGRES_USER` and `POSTGRES_DB` both
default to `opendiving` and can be overridden in `.env` before the first start (afterwards they name
a database that already exists under a different name).

| Variable                 | Default       | What it does                                                                                                                                                                                                                                                                                                                                               |
| ------------------------ | ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `MIGRATE_ON_START`       | `true`        | Runs `alembic upgrade head` as the API starts, which is what makes an upgrade `pull` + `up -d`. Turn it off only if you'd rather run `docker compose run --rm api alembic upgrade head` yourself.                                                                                                                                                          |
| `REDIS_PASSWORD`         | *(none)*      | For pointing the app at a managed Redis instead of the bundled one. The bundled one needs no password and is not reachable outside the compose network.                                                                                                                                                                                                    |
| `FILE_STORAGE_BACKEND`   | `local`       | Where uploaded files are kept: `local` writes them into `FILE_STORAGE_DIR`, `s3` puts them in an S3-compatible bucket. The bundle mounts a volume for `local`, so a compose install on one machine has nothing to set here — see [Object storage](#object-storage) for the install that does. Any other value refuses to start.                             |
| `FILE_STORAGE_DIR`       | `/data/files` | Where the `local` backend writes uploaded dive-computer exports, c-card images, profile pictures and species photographs, inside the container. The compose file mounts the `files-data` volume there, so there is nothing to set unless you replaced that volume with a bind mount — and then the host directory has to be owned by uid 1000 or the API refuses to start. Ignored entirely under `s3`. |

Redis holds cache entries, open rate-limit windows and in-flight passkey challenges. Losing it costs
a cold cache and interrupts passkey sign-in until it is back (see [Sign-in](#sign-in)); nothing
durable lives there. What is durable lives in two places, and a backup has to cover both: the
records are in Postgres, and the uploaded files themselves are on the `files-data` volume — or in
your bucket, if you switched the backend below. See [backup-restore.md](backup-restore.md).

### Object storage

The default is a filesystem volume, and for almost every install that is the right answer: one
machine, one disk, no credentials to hold. `FILE_STORAGE_BACKEND=s3` is for the install where it is
not — a platform whose disk attaches to one service at a time, while both the `api` and the `worker`
container need the same files. Any S3-compatible store will do: Cloudflare R2, MinIO, Garage, Ceph,
Backblaze B2, AWS itself. Nothing about the app changes; the same uploads go to a bucket instead of a
directory, under the same names.

| Variable                                   | Default  | What it does                                                                                                                                                                                                            |
| ------------------------------------------ | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `S3_ENDPOINT_URL`                          | *(none)* | The store's full origin, scheme included — `https://<account-id>.eu.r2.cloudflarestorage.com` for R2, `http://minio:9000` for a MinIO beside this stack. There is no default because every store's is different.       |
| `S3_BUCKET`                                | *(none)* | The bucket. It has to exist already; nothing here creates one.                                                                                                                                                          |
| `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | *(none)* | The credential. It needs to read, write, delete and list inside that one bucket, and nothing beyond it.                                                                                                                 |
| `S3_REGION`                                | `auto`   | `auto` is what R2 documents and what every other S3-compatible store ignores. A real AWS bucket needs its own region here instead.                                                                                      |
| `S3_PREFIX`                                | *(none)* | An optional key prefix, for sharing one bucket between instances. Prepended to every object name. The keys the database holds are the same either way, so adding or removing it later means moving the objects to match. |

**The first four are required, and startup enforces it.** With `FILE_STORAGE_BACKEND=s3` and any of
them unset, the API refuses to start and names the ones that are missing, rather than starting and
failing on the first diver's upload. Then it writes a probe object and deletes it again, so a wrong
bucket name, a credential that can read but not write, or a bucket in somebody else's account fails
at `docker compose up -d` with the endpoint and the bucket in the message.

**The worker needs the credentials too**, and the compose file already hands them over — `.env` goes
to `api` and `worker` wholesale, so there is nothing extra to set. It is worth knowing why it
matters: the worker is what destroys a deleted account's files once the grace period runs out (see
[Account deletion](#account-deletion)), and it runs that same probe at startup, so a worker that
cannot reach the bucket dies loudly instead of reporting erasures it did not perform. The
`files-data` mount on both services goes unused under `s3`; leave it there, and switching back stays
one variable.

**Keep the bucket private.** Every byte is served through the API, which reads the object and hands
it to a request it has already authorised — nothing generates a public or pre-signed URL, so a
bucket that allows anonymous reads is not enabling anything, only exposing c-card scans to whoever
guesses a key.

**Deletions land just after the job, not at the click.** What a purge destroys is unchanged, but on
`s3` the objects go in a request the app does not wait for: the transaction commits, the rows are
gone, and the delete follows a moment later on a background thread — because waiting for a round trip
to the store there would stall everything else the process is serving. So a bucket you are watching
may still list a purged account's keys for a few seconds. If one fails, it is logged and the object
becomes an orphan, which is what the sweeper reclaims:

```bash
docker compose exec api python -m src.scripts.sweep_orphaned_files          # report only
docker compose exec api python -m src.scripts.sweep_orphaned_files --delete
```

**Switching between the two backends is a copy, not a migration** — the key a row carries is the same
string on both, which is why nothing in the database has to change. Put the `S3_*` group in `.env`
and leave `FILE_STORAGE_BACKEND` naming the backend you are moving *away* from, so that both are
configured at once. Then recreate the containers, and copy:

```bash
docker compose up -d
docker compose exec api python -m src.scripts.migrate_blobs --to s3
```

That `up -d` is doing real work, and skipping it fails in a confusing way. `exec` runs a process
inside a container that still holds the environment it was *created* with, so on the container
started before you edited `.env` the copy refuses, saying the `S3_*` group is unset — while you are
looking at it in `.env`. It is the trap the top of this page warns about, met in the one procedure
here that reaches into a running container rather than restarting it.

The copy never deletes from the source, and it is resumable: every key ends in the sha256 of its own
content, so an object already sitting under that key cannot hold different bytes and is skipped
rather than re-sent. Interrupt it and run it again. When it reports no failures, set
`FILE_STORAGE_BACKEND` to the backend you copied *into* and `docker compose up -d` once more — that
second recreate is what actually moves the instance across.

`--to local` runs the same procedure in the other direction, with the two backend names swapped
throughout.

Run it against a quiet instance. Anything uploaded after the copy has walked past its key stays on
the old backend, and its row will point at bytes the new one does not have — a second run after the
switch catches whatever arrived in between. Reclaiming the old copy is a separate, deliberate step
once the new backend has been seen to serve: `docker volume rm opendiving_files-data` with the stack
down, or the bucket's own lifecycle rules going the other way.

## Optional features

| Variable                                                                                                           | Default             | What it does                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| ------------------------------------------------------------------------------------------------------------------ | ------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `CONTACT_FORM_EMAIL`                                                                                               | *(none)*            | Where the contact form delivers. Unset, that endpoint answers 503 and the form is off.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `CONTACT_EMAIL`                                                                                                    | *(none)*            | Shown on the contact page as a fallback. Display only.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `GOOGLE_CLIENT_ID`                                                                                                 | *(none)*            | Offers Google Sign-In, which needs an OAuth client of your own — see [Setting up Google sign-in](#setting-up-google-sign-in). Nothing of Google's loads in a visitor's browser; pressing the button takes them to Google. Unset, the button is hidden.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `GOOGLE_CLIENT_SECRET`                                                                                             | *(none)*            | The other half of that OAuth client, and a real secret. Required whenever `GOOGLE_CLIENT_ID` is set — the API refuses to start without it. See [Setting up Google sign-in](#setting-up-google-sign-in).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `MAP_STYLE_URL`, `MAP_STYLE_URL_DARK`                                                                              | OpenFreeMap         | A MapLibre vector style of your own, in place of the pair the web image ships — see [Third-party calls](#third-party-calls). Wins over the raster group below outright, on every map the app draws, leaving those variables inert. The dark one falls back to the light one; setting it alone does nothing. Serve the style's tiles, glyphs and sprite from the style URL's own host: that origin is the only one the CSP admits, so a style reaching a second host draws blank.                                                                                                                                                                                                                                                                                                                            |
| `MAP_ATTRIBUTION`                                                                                                  | the basemap's       | The credit drawn over whichever basemap is active — one variable, not one per mode, which is why it is no longer `MAP_TILE_ATTRIBUTION`. **Required whenever `MAP_STYLE_URL` is set**: the app refuses to serve without it, because it cannot know what your style's licence asks for.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `MAP_TILE_URL`, `MAP_TILE_URL_DARK`, `MAP_TILE_API_KEY`                                                            | *(none)*            | The raster escape hatch, in `{z}/{x}/{y}` form, for a tile server you run or a keyed provider. A whole-map mode chosen instead of the vector default, not a second renderer: MapLibre wraps the template into a minimal style. Ignored entirely when `MAP_STYLE_URL` is set. The CSP follows all of these automatically.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| `GEOCODER_URL`                                                                                                     | Nominatim           | Turns a map pin into a place name, server-side. Set to `""` to switch geocoding off entirely.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| `GEOCODER_USER_AGENT`                                                                                              | the project's       | The `User-Agent` on every geocoder call, and the only place it is sent. Ships as `OpenDiving (+https://github.com/opendiving/opendiving-api)`. It fails closed harder than `SPECIES_USER_AGENT` does: Nominatim answers **403** to an empty value *and* to a merely generic one — `python-httpx/0.27` was measured taking the same 403 as `""`, where the shipped default takes a 200. Geocoding is no optional enrichment either, so a generic value costs all three things it backs — place search on the dive site form, place search on the trip form, and naming the spot behind a pin — and leaves an instance indistinguishable from `GEOCODER_URL=""`: search answers with nothing, reverse with "we could not ask", the API stays healthy, and no log line names the 403. Change it because the default identifies the *project*, not your instance — see [Third-party calls](#third-party-calls). |
| `WORMS_API_URL`, `WIKIDATA_API_URL`                                                                                | public              | The two name registers the species picker searches, called server-side. WoRMS is the taxonomic authority every catalog row is keyed on; Wikidata supplies the common names it lacks — WoRMS records exactly one vernacular for the clownfish, and it is in Japanese. Emptying one does not switch the feature off the way `GEOCODER_URL` does: search falls back to the species already in your catalog, and resolving one nobody has logged yet fails.                                                                                                                                                                                                                                                                                                                                                     |
| `COMMONS_API_URL`                                                                                                  | public              | Wikimedia Commons, asked for a species photo's credit metadata and the URL of one scaled copy, once Wikidata has named the file — never for anything a diver typed. This one *is* optional in the way the two above are not: `""` or an unreachable host simply means species have no photos. It configures the **metadata** call only. The image bytes are only ever fetched from `thumb.wikimedia.org` or `upload.wikimedia.org`, the two hosts one Commons reply can name; that pair is hard-coded and deliberately has no setting in front of it, because it is an SSRF fence — see [Third-party calls](#third-party-calls).                                                                                                                                                                            |
| `SPECIES_USER_AGENT`                                                                                               | the project's       | The `User-Agent` on every species call — both registers, and Commons for the credit metadata and the image bytes. Ships as `OpenDiving (+https://github.com/opendiving/opendiving-api)`. Emptying it is **not** the graceful off switch the row above is: Wikimedia answers **403** to an empty one, on the metadata call and the byte fetch both, and the same header goes to WoRMS and Wikidata — so a blank value takes species search and resolution with it, not only the photos, and the API starts normally either way. Change it because the default identifies the *project*, not your instance: every deployment sends that one string, so one operator's runaway backfill is attributed to everyone running OpenDiving; put your own contact in — see [Third-party calls](#third-party-calls).   |
| `SPECIES_WORMS_RATE_LIMIT_REQUESTS`, `SPECIES_WIKIDATA_RATE_LIMIT_REQUESTS`, `SPECIES_COMMONS_RATE_LIMIT_REQUESTS` | `120`, `300`, `120` | What the whole instance may spend on each upstream, over `SPECIES_WORMS_RATE_LIMIT_WINDOW_SECONDS`, `SPECIES_WIKIDATA_RATE_LIMIT_WINDOW_SECONDS` and `SPECIES_COMMONS_RATE_LIMIT_WINDOW_SECONDS` — `60` seconds each. Counted across every user and charged only to calls that actually leave, so exceeding one is never a 429: that upstream drops out and the rest still answer. Neither provider publishes a limit — WoRMS states none at all, and Wikimedia's applies to anonymous heavy use rather than to a call every few seconds — so all three are self-imposed politeness, set well above what a picker generates. Commons's is lower than Wikidata's and still ample — it is charged at most twice per *new* species, the credit call and the byte fetch, rather than once per search candidate. |

### Account deletion

| Variable                      | Default | What it does                                                                                                              |
| ----------------------------- | ------- | ------------------------------------------------------------------------------------------------------------------------- |
| `ACCOUNT_DELETION_GRACE_DAYS` | `14`    | How long a deleted account stays restorable before it and everything it owns are destroyed. `0` purges on the next sweep. |

Deleting an account takes effect immediately — the app stops opening, on every device — but the data
is not destroyed until the grace period runs out. A cron in the `worker` container runs hourly at
:30 and issues a real `DELETE FROM "user"` for each account past its deadline, taking that diver's
dives, dive sites, certifications, gear, trips and every uploaded file with it. Nothing else purges
an account, and nothing decides on a user's behalf that one should go: the job only ever executes a
request the user already made.

**Two things worth knowing before you change the number.** The bundled privacy page states that
personal information is permanently deleted within 30 days. That sentence is true at the default and
stays true up to about 29 days; raise this past that and the page your instance serves is making a
promise your configuration breaks. And at `0` there is no way back at all — the confirmation email
says so instead of naming a date, but a misclick is then final.

**You are the controller.** OpenDiving is software; the operator of an instance is who data
protection law has obligations for. This setting is the knob that erasure requests are served by —
what it does, and how promptly, is your call to make and to document.

**Two things the purge cannot reach**, and both are yours to handle rather than the app's. Your
backups keep a deleted account until they rotate, and restoring one older than the request brings
that account back — see [backup-restore.md](backup-restore.md). And if you have turned the admin
panel on, its own event and audit tables hold a second copy of whatever you edited there; see
[The admin panel](#the-admin-panel).

### The admin panel

Off by default, and a deliberate opt-in: it is a full CRUD interface over every model and bypasses
the ownership checks the API applies to everything else. It is **not** where you work the invite
queue — that is the app's own [Admin section](#who-may-create-an-account), which needs none of this.

```bash
CRUD_ADMIN_ENABLED=true
ADMIN_PASSWORD=a-real-password        # production refuses to start without one
ADMIN_USERNAME=admin
CRUD_ADMIN_MOUNT_PATH=/crud-admin     # required now: /admin is the app's own admin section
CRUD_ADMIN_ALLOWED_NETWORKS=10.0.0.0/8   # optional, comma-separated
```

**`CRUD_ADMIN_MOUNT_PATH` is the line that is new, and enabling the panel without it gets you the
wrong page.** The panel still defaults to `/admin`, and `/admin` is now a page of the web app, which
is where the bundled Caddyfile sends it. Move the panel somewhere else and the two stop colliding —
then add a route for the path you chose, since the bundle routes only what it knows about. The
Caddyfile carries a commented-out block for exactly this at the top; for your own proxy it is one
more `location` or router, alongside the one in [reverse-proxy.md](reverse-proxy.md).

The compose file already points its tables at the app's Postgres (`CRUD_ADMIN_DB_URL`), which is
what makes it work behind four API workers. If your `POSTGRES_PASSWORD` contains `@`, `/`, `:` or
`#`, percent-encode it in that derived URL.

The allowlist matches the caller's address only when `TRUSTED_PROXY_IPS` names the proxy actually in
front of the app — the panel's own middleware reads the forwarded address the app was told to
believe. The same setting is what stops the panel redirecting its own path to the HTTPS URL it is
already on: it enforces HTTPS on `ENVIRONMENT=production`, and a proxy the app hasn't been told
about makes every request look like plain HTTP. Both symptoms are one misconfiguration, and the
shipped value covers the bundled Caddy.

Running your own proxy? The panel is the one thing a single `web:3000` upstream does not carry, so
route whatever you set `CRUD_ADMIN_MOUNT_PATH` to at `api:8000` yourself — and make sure your proxy
is in `TRUSTED_PROXY_IPS` **and** sets `X-Forwarded-Proto`. Nothing else needs splitting out:
`/admin` is a page of the web app and reaches the API the way every other page does.

**The panel signs its administrators in with cookies of its own**, set under `CRUD_ADMIN_MOUNT_PATH`
when someone logs in to it. They are part of the surface you operate rather than anything a diver
meets: nobody using the app receives one, and they exist only in the browser of whoever administers
this copy. That is why the bundled privacy page — written for the people whose dives your instance
holds — does not describe them, and points operators here instead. They belong to `crudadmin` and
their names are its business, not this app's, so read them out of your own browser rather than from
a list here that a dependency upgrade could quietly falsify. Leave the panel off, as it ships, and
there are none.

**Turning it on gives you a second copy of personal data, and account deletion does not reach it.**
The panel keeps its own tables — `admin_event_log`, a row per action with the admin's address and
user agent, and `admin_audit_log`, which for every create, update and delete stores the row's JSON
state *before* and *after*. Edit a diver through the panel and their email address is now in that
audit row as well as on the `user` row. One setting gates both tables, `CRUD_ADMIN_TRACK_EVENTS`,
and it defaults to on — so enabling the panel enables these unless you say otherwise. They live
wherever `CRUD_ADMIN_DB_URL` points, which the compose file points at the app's own Postgres, so a
`pg_dump` carries them too.

The [account purge](#account-deletion) deliberately leaves them alone. Those tables have no foreign
key to `user` and a different lifecycle: they are a record of what *an operator* did, which is the
one thing an audit log is for, and a purge that quietly rewrote it would be an audit log worth
nothing.

That makes them yours to manage, and nothing manages them for you — `crudadmin` has a retention
helper but nothing in this app calls it, so both tables grow for as long as the panel is enabled. If
you turn it on, prune them yourself on whatever schedule matches what you tell your users:

```bash
docker compose exec -T db psql -U opendiving -d opendiving \
  -c "DELETE FROM admin_audit_log WHERE timestamp < now() - interval '90 days';" \
  -c "DELETE FROM admin_event_log WHERE timestamp < now() - interval '90 days';"
```

Audit rows carry the id of the event they belong to, but not as a foreign key — nothing stops you
deleting the events and leaving the audit rows pointing at nothing, so keep the two windows the
same. And when you serve an erasure request for someone whose row you once edited by hand, remember
this copy. Leave the panel off, as it ships, and none of this exists.

## Third-party calls

Nothing here phones home. What the app can be told to contact:

- **From the browser**: the basemap. Nothing else, in any configuration — profile pictures and
  species photographs included. An avatar is stored by your own instance and served by your own
  API, and so is the Commons photograph on a species: the server fetches it once and stores it, so
  no visitor's browser ever contacts Wikimedia. (Gravatar used to be an option here, disclosing a
  hash of every signed-in user's email address and their IP to Automattic on every page. It is gone,
  along with its `GRAVATAR_ENABLED` variable.)

  **The basemap** is fetched wherever a map is on screen, and each request carries only the `z/x/y`
  of the area shown. Unconfigured, that is the MapLibre vector pair the web image ships — its
  tiles, its label glyphs and a low-zoom raster underlay, all from `tiles.openfreemap.org`. Five
  surfaces draw a map: the form to add or edit a dive site, a dive site's own page, the form to add
  or edit a trip, a trip with places on it, and the page of a dive that has a position — from the
  site it was logged at, or from the GPS reading in the file it was imported from. The two forms
  load a map as soon as they open; the other three load none when there is nothing to show. Whoever
  serves the basemap therefore sees a visitor's IP address and roughly where they dive, and nothing
  else — not their account, their dive log, or the name of anything on the map.

  **Removing the third party takes one variable.** All five surfaces draw through MapLibre, so a
  single setting reaches every one of them: `MAP_STYLE_URL` for a vector style you serve, or
  `MAP_TILE_URL` for a raster tile server you run. The two are alternatives rather than layers — a
  style set alongside the raster group leaves it inert — so there is no second fetch to close off
  separately. The shipped default contacts one host, `tiles.openfreemap.org`, and pointing either
  variable at something you serve is what stops anything leaving your machine.

  The raster group is a whole-map mode, not a second renderer: MapLibre wraps a `{z}/{x}/{y}`
  template into a minimal style and draws it the way it draws a vector one. It stays as the escape
  hatch — for a tile server you already run, or a keyed provider you prefer.

  **Google sign-in is deliberately absent from that bullet**, and it is worth saying why rather than
  leaving it to be inferred. With `GOOGLE_CLIENT_ID` set, no page this app serves fetches, embeds or
  executes anything of Google's — the front page and the sign-in page included, and whether or not
  the visitor ever intends to use the button. What pressing "Continue with Google" does is send the
  browser *away*: a top-level navigation to `accounts.google.com`, where the visitor is on Google's
  own site under Google's own policy. Whatever Google stores at that point, it stores as the site
  being visited rather than as a third party embedded in yours. The URL necessarily tells Google
  which instance sent them — it has to carry your client id and the address to come back to — and
  that, together with whatever they choose to do on Google's own page, is the whole of it. They
  return carrying a one-time code, and turning that code into a sign-in happens between your API and
  Google, never in the browser.

  Leaving `GOOGLE_CLIENT_ID` unset still removes the option entirely: no button, and the bundled
  privacy page has no Google section at all.

- **From the server**: the geocoder and the two species *name registers*, WoRMS and Wikidata, on
  cache misses only. A pinned coordinate or a typed search string goes out; nothing identifying the
  diver does, and the source IP is your server's. All three are configurable, and the geocoder can
  be switched off outright.

  **Wikimedia Commons is a fourth, and it is not one of those registers.** It is never asked
  anything a diver typed — it receives a file title derived from an AphiaID, and answers with a
  photograph's credit metadata and the URL of one scaled copy, which the server then fetches. That
  is not a cache miss on a search: it happens once, when a species is first resolved into your
  catalog, and again for species already in it whenever an operator runs the photo backfill script
  in the API container by hand — nothing runs it on a schedule. `COMMONS_API_URL` points the
  metadata call at a mirror, and `""` switches species photos off entirely. The image bytes
  themselves are only ever fetched from `thumb.wikimedia.org` or `upload.wikimedia.org` — one
  Commons reply names both, the scaled copy on the first and the full-size original on the second
  for a file already small enough to serve whole. Those two hostnames are hard-coded and have no
  setting, because that is an SSRF fence and a fence with an environment variable in front of it is
  not a fence.

  **Every one of those species calls carries the same `User-Agent`**, `SPECIES_USER_AGENT` — the two
  registers, the Commons metadata call and the byte fetch. It says what the software is, never who
  the diver is, and both upstreams want it: WoRMS asks to be told who is calling, and
  [Wikimedia's policy](https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy)
  requires one. **Unlike `COMMONS_API_URL` it is not an off switch.** An empty value was measured
  answering 403 on the Commons metadata call and on the image bytes alike, and the registers carry
  the same header, so blanking it costs species search and resolution rather than only the photos —
  and nothing warns you, because the API starts and serves normally either way. The default
  identifies this project rather than your deployment, which is the reason to change it on a public
  instance: every install that leaves it alone is one indistinguishable client to Wikimedia, so one
  operator's runaway backfill is attributed to everybody running OpenDiving.

  **The geocoder carries its own, `GEOCODER_USER_AGENT`, and Nominatim is stricter about it.**
  [Its usage policy](https://operations.osmfoundation.org/policies/nominatim/) asks for "a valid HTTP
  Referer or User-Agent identifying the application", and adds that a stock one set by an HTTP
  library will not do — which is enforced rather than advisory. Measured against the public instance
  on 2026-08-31: an empty agent **403**, a plain `python-httpx/0.27` **403**, the shipped default
  200. That middle result is what makes this header unlike the species one — non-empty is not
  enough. And geocoding is not an enrichment that can quietly drop out. Three surfaces rest on it —
  the place search on the dive site form, the place search on the trip form, and naming the spot
  behind a pin — so a proxy that rewrites outbound headers, or a generic string pasted in, takes all
  three at once. What is left is exactly what `GEOCODER_URL=""` gives — search returns nothing,
  reverse returns "we could not ask", the API stays healthy — and the only trace is a log line
  naming the exception class, never the 403. The reason to change it on a public instance is the one
  above, and it is **not** that the default is generic: it is not, and it is accepted. It identifies
  the project rather than your deployment, so every OpenDiving instance arrives at Nominatim under
  the same name — leaving its operators no way to tell one from another, or to reach the one giving
  them trouble. Put your own project and contact address in.

  Two more, only if you have set `GOOGLE_CLIENT_ID`. **Every Google sign-in redeems its authorization
  code** at `oauth2.googleapis.com`, over TLS from your server, using `GOOGLE_CLIENT_SECRET` — that
  call is on the sign-in path itself, so an instance whose outbound traffic is filtered has to allow
  it. And **when somebody signs up with Google**, the API fetches their Google profile picture once
  — from `googleusercontent.com`, at account creation and never again — and stores it with everything
  else you host. That one is best-effort; a failure just means the account starts with initials.

There is no analytics of any kind. The web app's Content-Security-Policy narrows where anything
could be *sent*: `connect-src` names this instance's own origin, its API and the host serving the
basemap, and nothing else, in every configuration, so a `fetch`, an `XMLHttpRequest`, a WebSocket or
a `navigator.sendBeacon` aimed at a third-party collector is refused by the browser until the policy
itself is widened. (The basemap sits in that directive in both of its modes rather than in
`img-src`, because MapLibre decodes even raster tile bytes from an `ArrayBuffer` it fetched. So
`img-src` names no third-party host at all, in any configuration — `'self'`, `data:`, `blob:` and
this instance's own API, and nothing else.)
Google sign-in needs no exception to that and is granted none — a navigation is not a fetch, and
CSP's fetch directives govern what a page loads rather than where the visitor goes next. Take that
for what it is and no more — it constrains destinations, not dependencies. Script bundled into the
web app loads under `'strict-dynamic'`, because your own build already vouches for it, and anything
reporting back to this instance's own origin passes as ordinary first-party traffic.

**Add any of it and the consent duty is yours.** The `/privacy` page is part of the web image, and
it describes exactly the posture above: nothing here is advertising or analytics, which is the whole
reason it offers no cookie banner. Add a tracker, an analytics script, an advertising tag or any new
third-party subresource to your copy and two things happen together — that page stops being true of
your instance, and asking for consent *before* the storage or access happens becomes an obligation
on you, along with building the flow that collects it. Under ePrivacy that duty falls on whoever
operates the service, which is you and not this project, and nothing in the image can discharge it
on your behalf.
