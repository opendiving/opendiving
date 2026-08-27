# Decisions

Why things here are the way they are. Read the relevant section before changing something
unfamiliar; append to it when you make a choice whose reasoning would not survive being guessed at.

This file starts short on purpose. The bundle's own rationale still lives in
[`opendiving-api`'s DECISIONS.md](https://github.com/opendiving/opendiving-api/blob/main/DECISIONS.md)
and moves here section by section as that repository hands it over. What is recorded below is what
this repository's *existence* decided.

## Why a product repository at all

The install lived in `opendiving-api` because that is where it was first written, and it was never
an api-level thing: `docker-compose.yml` pins the web image and sets `SITE_URL`, `GOOGLE_CLIENT_ID`,
`MAP_TILE_*`, `WEB_HSTS` and `WEB_NOINDEX`, none of which the API has any use for. Two consequences
made the accident worth undoing.

The first is that the project had no front door. `opendiving-api`'s README opened "The backend for
OpenDiving" and then carried the four-command install and the sentence "That is the whole product";
`opendiving-web`'s README carried the actual pitch and the only screenshots and offered no way to
install anything. Every place a project gets named once — an awesome-selfhosted entry, a Show HN, a
link in a forum thread — had to point at a component and hope.

The second is the release. A per-repository workflow can check that its own tag matches its own
manifest, and cannot check its sibling at all; the lockstep ritual therefore carried a step telling
a human to look at GHCR and confirm the web image existed before publishing the api release. That
step is now `.github/workflows/release.yml`.

## The release runs last, and that is what makes the guard possible

`opendiving-api` and `opendiving-web` publish images on their own tags. This repository is tagged
**after** both, and its only job before publishing is to look: both images, at this exact version,
each carrying `linux/amd64` and `linux/arm64`.

Ordering is the whole mechanism. Asked at any earlier point the question is "will these exist?",
which needs polling, a timeout and a decision about what to do when it expires; asked last it is
"do these exist?", which is one `imagetools inspect` per image and a clean failure.

The architecture half is not padding. A release whose arm64 leg failed to push still has an `X.Y.Z`
tag that resolves perfectly well, and the first person to discover otherwise is somebody installing
on a Raspberry Pi — roughly half this project's audience. A half-published manifest is worse than a
missing one, because it fails for a subset of people and looks fine to everyone testing it.

## No version manifest here

`opendiving-api` guards its tag against `pyproject.toml` and `opendiving-web` against
`package.json`, because each is publishing an image built from that tree and a tag disagreeing with
the manifest is a silent mislabelling.

This repository publishes no image. A `VERSION` file here would be a third thing to bump, able to
disagree with the other two, guarding nothing — and the check that actually matters, "do both images
exist at this version", is strictly stronger and needs no local record of what the version is
supposed to be.

## Digests are pinned here and floated there

The three third-party images are pinned `tag@sha256:...`. Nothing in this repository is built: an
operator *pulls*, so a floating tag would hand them whatever upstream published this morning rather
than the bytes the bundle was tested against.

`opendiving-api`'s Dockerfile does the opposite deliberately, floating on `python:3.14-slim-bookworm`,
because that one *is* built and the float is what makes a CVE rebuild work at all — re-running its
publish workflow at an old tag picks up patched Debian packages precisely because the base resolves
at build time. Digest-pin it and the rebuild reproduces the vulnerable base byte for byte.

Both are right. Renovate is configured here with `pinDigests: false` for the same reason it is
there: its job is to renew whichever style it finds, not to normalise them into one.

## `example.env`, not `.env.example`

GitHub renames a release asset whose name starts with a dot. Uploaded as `.env.example` it is stored
as `default.env.example`, the documented `releases/latest/download/.env.example` URL 404s, and the
workflow reports success. Verified by uploading one; Immich ships `example.env` as the same
workaround.

The cost is a filename that disagrees with the `.env.example` convention both code repositories use,
which is why this is written down: it looks exactly like an inconsistency worth tidying.

## `install.sh` fills the template in; it does not write a `.env`

The obvious shape for an installer is to collect the answers and write a small `.env` out of them.
Here that would throw away the most useful file in the bundle. `example.env` is almost entirely
comments: a handful of settings, and beside each one what it does, what it costs and what goes
wrong when it is wrong — all the documentation an operator has at 1am, holding a few files and no
repository.

So the script downloads the template and rewrites the value on the few lines an install cannot
start without, leaving every comment where it was. The check is a `diff` of the template and the result with values stripped: it
has to be identical line for line, or a comment went missing. `AGENTS.md` carries the command.

The same reasoning rules out the other tempting shape, a script that prompts its way through every
setting. It fills in what an install cannot start without, plus `SMTP_TLS_MODE` in the one case
where the port chosen makes the template's default wrong. Everything else in `example.env` is
commented out on purpose, and reading the paragraph above a setting is how an operator decides
whether they want it.

## A value is written the way Compose reads it back

A bare value in `.env` is not literal. Compose stops it at the first ` #` and expands `$` in it, so
`SMTP_PASSWORD=pa$$w0rd # 1` reaches the API as `pa` — no error, no warning, and the first thing to
notice is a sign-in email that never sends. That is not a guess: `docker compose config` prints the
value each service will actually get, which is how each case below was settled.

Single quotes are literal and carry everything except a single quote. So the script writes anything
outside `[A-Za-z0-9_@%+=:,./-]` single-quoted, and a value containing a quote of its own
double-quoted with `\`, `"` and `$` escaped. The by-hand path has exactly the same trap, which is
why `docs/install.md` now says so under the table of six values.

## The generated secrets are hex

`docs/install.md` suggests `openssl rand -base64 24` for `POSTGRES_PASSWORD`, which is fine for a
human reading the paragraph next to it: base64's alphabet includes `/` and `+`, and a password
containing `@ : / #` has to be percent-encoded again in the `CRUD_ADMIN_DB_URL` that
`docker-compose.yml` derives. A generated value has no reason to inherit that. Twenty-four random
bytes as hex is the same 192 bits over an alphabet that needs escaping nowhere.

`openssl rand -hex` when openssl is installed, `od -An -vN <bytes> -tx1 /dev/urandom` when it is
not. The `-v` matters: `od` collapses repeated identical lines into `*`, which would silently
shorten a secret on the input that happens to repeat.

## `--version` pins both halves

The flag picks the release the bundle is downloaded from *and* writes `OPENDIVING_VERSION` into the
`.env`. Only the first half is obvious, and only the first half is what the flag looks like it
means — but `docker-compose.yml` resolves both OpenDiving images through
`${OPENDIVING_VERSION:-latest}`, so pinning the files alone would hand somebody who asked for
`v0.3.0` the newest images running against a compose file three releases old. That combination is
both the one nobody wants and the one hardest to notice, because everything starts.

## The DNS check asks this machine, not a stranger

A domain that does not resolve here is the most common failed install, and the failure surfaces as
Caddy failing an ACME challenge minutes later. The script checks it up front — but against the
addresses this machine actually holds, never by asking an outside "what is my IP" service. Pointing
a self-hosting install script at a third party to learn something it can only get half right is the
wrong trade, and behind NAT the two answers differ for a perfectly good reason. Hence a warning and
never a refusal.

## What it refuses to do

- **Start the stack.** Caddy asks Let's Encrypt for a certificate the moment it comes up, and failed
  challenges are rate-limited per hostname per hour. Whether DNS has propagated is the operator's
  call, so the script prints `docker compose up -d` and stops.
- **Overwrite an existing `.env`.** `POSTGRES_PASSWORD` is read once, when the `db` volume is
  created, and never again: a regenerated one leaves a database the new `.env` cannot open, and the
  failure reads as an authentication bug rather than a config one. The script exits and says so.
- **Install Docker.** It detects and points at the official instructions. A script that pipes a
  package manager and root into another downloaded script is not a convenience worth having, and
  the distribution-specific parts are exactly where it would rot.

## `docs/` is flat

The docs arrived from `docs/self-hosting/` in `opendiving-api`, where the prefix distinguished them
from `docs/authentication.md` and anything else that repository documents. Here there is nothing to
distinguish them from — a `self-hosting/` directory in a repository that is only self-hosting is a
directory for nothing.

All nineteen cross-links between the six documents were sibling-relative and survived the move
untouched. The single link that pointed out of the old tree, `configuration.md`'s reference to
`../../src/.env.example`, is now a URL into `opendiving-api` — which is the general rule here, and
the one thing to get right when moving text between these repositories.

## Operator issues here, application bugs next door

An issue about installing, upgrading, backing up or configuring belongs in this repository; a bug in
the app belongs in `opendiving-api` or `opendiving-web`. The docs' "still stuck?" links and
`SECURITY.md` both route on that line.

It is a soft line and deliberately so — told to guess, people guess wrong, and an issue in the wrong
repository costs one move. Both `README.md` and `SECURITY.md` say so explicitly rather than
presenting the split as something the reporter has to get right.
