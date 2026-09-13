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
`MAP_*`, `WEB_HSTS` and `WEB_NOINDEX`, none of which the API has any use for. Two consequences
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

## The GHCR login outlives the reason it was added

The release workflow logs in to GHCR before inspecting the two images. That step was load-bearing
while `opendiving-api` and `opendiving-web` published private packages; both are public now, the
inspect resolves anonymously, and the step reads as dead code to anybody sweeping for leftovers from
the flip. It is kept anyway, because the failure it protects against is the one this guard cannot
report honestly: a package made private again — during an embargoed security fix, say — is invisible
to a workflow that has not been granted access to it, and `imagetools inspect` answers with a
manifest-unknown that is indistinguishable from the image not being there. The step's own error then
says "does not exist" and sends whoever reads it to re-run a publish that already succeeded.

Leaving it in costs one round trip and keeps `packages: read` honest in the permissions block. Taking
it out saves nothing and buys a wrong answer on the day it matters.

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
has to be identical line for line, or a comment went missing. `CONTRIBUTING.md` carries the command.

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

For the same reason the flag turns off the shortcut that installs the bundle sitting next to the
script instead of downloading one. That shortcut exists so a change to these files can be tested
before it is tagged; combined with `--version` it would install a working tree while pinning images
to a release — a version skew of exactly the kind the flag is there to prevent.

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

## `MAP_TILE_API_KEY` is documented as public, not as a secret

`configuration.md` lists it beside `SECRET_KEY`, `POSTGRES_PASSWORD` and `SMTP_PASSWORD`, and it is
the one in that neighbourhood that an operator must *not* treat the way they treat the others. The
basemap is drawn by MapLibre in the visitor's browser, so the key is served to every browser that
loads a page with a map on it. `opendiving-web`'s `publicConfig()` (`src/lib/runtime-config.ts`)
builds the object handed to the client field by field, and `basemap` — the key included — is one of
the two fields in it.

So the docs say to use a key the provider has restricted to your own domain, rather than saying to
keep it safe, which is advice nothing can act on. It is said in three places — `example.env` beside
the setting, and twice in `configuration.md`, in the variable table and in *Third-party calls* —
because an operator reads whichever one they happen to open, and the instinct on meeting "API key"
in a server-side `.env` is that the server is where it stays. Every other secret in that file does.

The rule for changing any of the three is that the claim is about a *function next door*:
`opendiving-web`'s `publicConfig()` decides what reaches the browser, and if it ever stops carrying
`basemap` all three passages become wrong at once. Derive them with
`git grep -n MAP_TILE_API_KEY` rather than from this list.

## Self-hosting is a capability, not the product's identity

`README.md` calls OpenDiving "yours to self-host" rather than "a self-hosted dive log", and puts
"your own machine and your own Postgres" inside the sentence *about* self-hosting rather than
stating it as a standing fact about the product. `SECURITY.md` opens the same way. It is deliberate,
and it reads exactly like a tagline that lost its nerve.

What the software can promise every diver is the same wherever it runs: AGPL, every dive-computer
file you upload to a dive kept with it, and one click that takes everything out in open formats.
Where the data physically sits is a fact about *who runs a copy*, not about the app — the operator
of an instance decides that, which is the same line `docs/configuration.md` draws under **You are
the controller**. Copy defining the product as self-hosted-only makes that call on the operator's
behalf, and it is not the app's to make.

Self-hosting keeps the strong framing it earns: it is what turns data ownership from a promise into
a guarantee, it is the differentiator the Subsurface comparison turns on, and the licence section
still says run it, change it, self-host it freely. The change is register, not retreat.

**This repository's own framing is untouched.** It *is* the install bundle and the self-hosting
documentation, every page here is addressed to an operator on purpose, and none of that is what the
distinction is about — it is between describing this repository's job and defining the product.

## The hosted instance is named at the front door

The project operates one instance of its own software, at <https://opendiving.app> — invite-only, a
closed beta with a waitlist. `README.md` is where that URL is published, and the component
repositories send a reader here for it rather than repeating it; `opendiving-web`'s README says in
as many words that this is where "the instance this project runs itself is named". The reasoning is
*Why a product repository at all* above, applied to an address instead of an install: a component
repository publishing the product's front door would be the second front door the first one exists
to replace, and two of them drift the moment the address moves. `git grep -n opendiving.app` across
the three repositories is what derives that rather than trusting this paragraph, and its hits want
reading rather than counting: most of them are not this claim at all — the domain also carries the
project's mail addresses, an API origin and URL literals in tests — so the question to ask of each
is whether the prose around it sends a *reader* to the instance.

**One sentence on how the two relate is the whole of it**: the same code at the same release, with
the project as that instance's operator instead of you. It is deliberately not a pitch. This
repository is the install bundle, every page in it is addressed to somebody running their own copy,
and a hosted instance sold hard at the top of its README would be reading the room backwards. The
section above draws the same line from the other side: what the software promises is the same
wherever it runs, and who operates a copy is a fact about the copy.

`SECURITY.md` carries the consequence that is not cosmetic. "Test against a copy you run yourself"
was unambiguous while no instance was the project's; now that one is, the policy has to say out loud
that the project's own instance is not the exception — otherwise the most obvious target for a
well-meaning researcher is the one the maintainers answer for. The wording is `opendiving-api`'s,
matched rather than reinvented, so the two policies read as one.

**`PROJECT_OPERATED` gets no row in `docs/configuration.md`, and that is a ruling rather than an
oversight.** It is the API setting behind `project_operated` on `GET /api/v1/config`, and all it
selects is which voice the app's own copy speaks in — the project's, which says "join the waitlist",
rather than a generic operator's. A self-hoster has no use for it: switching it on makes their
instance speak as this project about a waitlist this project runs. Listing a setting in the operator
reference is an invitation to set it, so the reference stays silent and the absence is recorded here
instead — otherwise the next sweep for settings the reference is missing puts the row back, and the
sweep would be right to, because nothing else says why it is not there. Leaving it out costs the
file nothing it claims: `docs/configuration.md` opens by saying the API has more settings than it
lists and pointing at `opendiving-api`'s own annotated file for the full set, so the reference has
never been the exhaustive one.

## The template's registration line is `REGISTRATION_MODE=open`

A commented-out line in `example.env` is whatever the operator would actually type, and for a
two-state switch that is the *other* state: uncommenting a line that changes nothing is a decision
with no effect that reads as one with an effect. `# WEB_NOINDEX=true` sits against a default of
`off` and `# MIGRATE_ON_START=false` against `true`; `# REGISTRATION_MODE=open` against a default of
`invite` is the same shape, and it is the only value this setting gives anybody a reason to type.

Lines that are not switches are written differently in the same file, which is the rule applied
rather than broken. A number or a path appears at its **default** — `# INVITATIONS_PER_USER=5`,
`# LOG_LEVEL=INFO` — because the operator is adjusting a value rather than picking a state, and the
value they are moving away from is what helps them decide. A setting with more than two values
carries them in the paragraph and the default on the line (`# SMTP_TLS_MODE=starttls`), and one with
no default at all appears as a placeholder (`# CONTACT_FORM_EMAIL=you@example.com`).

Writing it the other way round — `# REGISTRATION_MODE=invite`, matching the default — would be worse
than redundant here. Uncommenting it changes nothing, so somebody who wanted the open behaviour and
uncommented the line they found would get a closed instance and no error, and the paragraph above it
would be explaining a value they already have. The paragraph is where the default is stated; the line
is the escape hatch.

The corollary is that `install.sh` does not ask about the mode. It fills in what an install cannot
start without, and the mode has a working default in both directions — see *`install.sh` fills the
template in* above. What it does do is say which mode the instance came up in, because a closing
message that stops at "the first account to sign in is yours" would leave an operator wondering why
the home page then asked them for an invite.

## Invite-only needs no compose change

`REGISTRATION_MODE` is an API setting and `docker-compose.yml` already passes the API the whole
`.env` (`env_file`), so it arrives with no edit. The web container gets a curated `environment:`
list instead, and deliberately gains nothing here: the web app learns the mode by asking the API for
it (`GET /api/v1/config`) rather than from a copy of its own.

That asymmetry is the whole reason the endpoint exists, and it is a property of *this* file rather
than a preference of the app's. A variable added to the web service's block is a change to a file
operators downloaded once — `docker compose pull` updates images, never the compose file — so a
web-side mirror of this setting would reach every new install and no existing one, and the failure
would be a landing page showing the wrong form on exactly the instances nobody re-downloaded
anything for. An endpoint ships inside the image and needs no cooperation from the bundle at all.

There is a second copy of this cost recorded next door: the web mirrors `GOOGLE_CLIENT_ID` in its
own environment and consequently cannot learn that the API is missing the matching secret, which is
why the API refuses to boot in that state. One mirror is enough.

## Object storage is documented here, not bundled

The API can keep uploads in an S3-compatible bucket. This bundle gains no MinIO service, no `s3`
compose profile and no new required variable for it, and that is the decision rather than an
omission.

The bundle's whole proposition is one machine with one disk: a named volume is already the simplest
correct answer there, needs no credentials, and is backed up by a `tar` an operator can read. Adding
a bundled object store would put a second stateful service into every install that does not want
one, and would quietly reframe the volume as the legacy path — which it is not. `s3` is for the
deployment this file is not for: a platform whose disk attaches to one service at a time, while both
the API and the worker need the same files. An operator on one of those already has a bucket and the
credentials for it; what they needed from this repository was the variable names, the fact that both
containers need the credentials, and the copy command — so what they get is
`docs/configuration.md`, `docs/backup-restore.md` and a commented block in `example.env`.

**The `files-data` mount stays on both services under `s3`**, unused. Compose can express a
conditional mount only through profiles, and a profile is a thing an operator has to know to set —
on a file they downloaded once and will not download again. An unused mount costs a directory; the
alternative costs a foot-gun on every switch back, which is otherwise one variable and a restart.

**The mount on `worker` is load-bearing on `local`, and the comment on it was wrong.** It said the
worker touched no stored file. The worker is what runs the account purge, so it deletes them — and
because the image creates `/data/files` owned by uid 1000, an unmounted worker has a perfectly
writable directory in its own layer, passes its own startup check, and reports successful erasures
that erased nothing. Nothing but that line prevents it. `opendiving-api`'s development compose
carries the same correction for the same reason; both were written when the purge did not exist yet.

## The operator commands are `python -m src.scripts.…`, and they do run in the shipped image

`docs/configuration.md` hands an operator `docker compose exec api python -m src.scripts.migrate_blobs`
and the orphan sweep beside it. Reading `opendiving-api`'s `Dockerfile`, that looks wrong: the
runtime stage copies only `src/app` to `/code/app`, plus the migrations and `alembic.ini`, so there
is no `src` tree under the working directory and the natural conclusion is `ModuleNotFoundError`.

The conclusion is wrong, and it has already been drawn once in review. The scripts arrive by the
other route: `pyproject.toml` declares `packages = ["src"]` for the wheel, the builder stage runs
`uv sync --locked --no-editable` — a real install of the project, not just its dependencies — and the
runtime stage copies the whole `/app/.venv` across. `src`, `src.app` and `src.scripts` are all in
`site-packages`, independent of anything under `/code`. Checked against the published image rather
than reasoned about:

```bash
docker compose exec api python -c "import src.scripts, sys; print(src.scripts.__file__)"
```

`opendiving-api`'s own `DECISIONS.md` generalises the opposite way, from an `admin_init` failure, to
"anything reached as `src.scripts.*` is a development tool by construction". That sentence does not
survive the command above — one of the three scripts it names runs from `site-packages` in the
published image with no bind mount. Re-run it before believing either entry; it is the only thing
that settles the question, and it is why an operator-facing command in a `src.scripts.*` shape is
worth a second look but not an automatic bug.

## `/admin` is the web app's, and the panel has to move

The bundled `Caddyfile` used to send `/admin*` to `api:8000`, because the only admin surface was
CRUDAdmin and CRUDAdmin mounts on the API. The app now has an admin section of its own — a
superuser-gated part of the web app, where the invite queue lives — at `/admin`, and it reaches the
API through `/api/v1` like every other page. So the matcher drops `/admin*` and the path falls
through to `web:3000` with everything else.

**This is a breaking change to the bundle, in the sense `CONTRIBUTING.md` defines**: an install that
pulls new images without taking the new `Caddyfile` keeps routing `/admin` to the API and cannot
reach its own admin section. Nothing warns them — they get the panel's login form, or a 404 where
the panel is off — which is why the release notes' Breaking section has to name the file rather than
only the setting.

The collision it creates is the other half. `CRUD_ADMIN_MOUNT_PATH` still defaults to `/admin`, so
an operator who enables the panel now has two things claiming one path and the routing decides: the
app wins, and the panel is unreachable. The fix is one line of `.env` plus a route, and it is
documented at every place the panel is — `example.env`, `docs/configuration.md`,
`docs/reverse-proxy.md`, `docs/troubleshooting.md` and a commented-out block in the `Caddyfile`
itself. *Rejected:* moving the panel's default in the API instead, which would be a second breaking
change for every install that had already enabled it, in service of a panel that is being retired
anyway; and keeping `/admin*` on the API and putting the app's section somewhere else, which would
have let the surface nobody uses keep the path the docs have always pointed operators at.

## Operator issues here, application bugs next door

An issue about installing, upgrading, backing up or configuring belongs in this repository; a bug in
the app belongs in `opendiving-api` or `opendiving-web`. Every place that sends a reporter *away*
routes on that line — derive them with `git grep -nE 'opendiving-(api|web)/(issues|security)'`
rather than trusting a list here, which is the kind of sentence that goes stale the first time a
surface is added. `docs/troubleshooting.md` points the other way, at this repository's own issue
form.

It is a soft line and deliberately so — told to guess, people guess wrong, and an issue in the wrong
repository costs one move. `README.md`, `SECURITY.md` and both issue templates say so explicitly
rather than presenting the split as something the reporter has to get right.

**Discussions live here rather than in a code repository.** The front door is the product's
repository: it is where `opendiving.app` sends people, where an operator's question already belongs,
and the only one of the three whose subject is the *whole* product rather than one half of its
implementation. The rejected alternative was `opendiving-api`, which is merely the oldest of the
three — a question about a chart would then be asked in the backend repository, and "ask in api,
report in web" is precisely the split the paragraph above exists to spare people. One space, at the
front door, is the version of this with nothing to get wrong.

This repository's `.github/ISSUE_TEMPLATE/config.yml` said it first, and `README.md`'s
**Contributing** section says it from the repository the space actually lives in — the one place
that can name it without pointing across a boundary. The other two configs were repointed here in
their own repositories, each in its own change, because a PR in one of the three cannot touch the
other two. Whether they still agree is not a thing to take this paragraph's word for:
`gh repo view opendiving/<repo> --json hasDiscussionsEnabled` says where the tab is enabled, and
`git grep -n discussions .github/ISSUE_TEMPLATE/config.yml` in each says where its links point. A
sentence claiming the three agree is written once and never re-checked; the two commands are.

## The README names the import formats, and `## Planned` keeps Shearwater

The API reads whatever the `divejson` converter reads, and builds every sentence it shows a diver —
the upload field's description, the "no reader claims this file" refusal — from the library's own
registry rather than from a list written out beside it, so those move on their own when the pinned
version does. This README cannot: it is prose, published, and read by somebody deciding whether to
install at all. It names the formats anyway, one by one, because "any format the converter reads"
tells a diver holding a `.ssrf` nothing, and telling them at a glance whether their file is one is
the entire point of the feature. The cost is that a version bump adding a reader leaves this list
short — a stale README rather than a wrong error message, and the fix belongs in the PR that bumps
the pin.

The pin is not in this repository, which is the part worth saying out loud: it is
`opendiving-api`'s, and a PR there cannot touch this file, so "the PR that bumps the pin" is a rule
spanning two repositories — the bump is not finished until a change here has named the new format.
Suunto's DM5 XML is the case that proved it: `divejson` 0.4.0 added the reader, the api's pin bump
switched it on, and this README went on omitting the format until a later PR caught up.

**Shearwater stays under `## Planned` even though Shearwater Cloud can export UDDF**, which the app
does read. What is still to come is the whole-database export, and having a database in hand moved
that blocker rather than clearing it: in the one export available to work from, the
`dive_log_records` table is empty and each dive's samples sit in `sw-pnf` blobs — the computer's own
log format — so the reader is a libdivecomputer-class binary parser rather than a walk over readable
rows. The bullet says so, because "no database to build the reader against" was the old reason and
reads as a much smaller obstacle than the real one. The `## How it compares` vendor-clouds bullet
keeps naming all four for the same reason it always did: it is a claim about those clouds'
*exports*, and every one of the four has one this app reads.

## "The original file is kept" is a claim about an upload to a dive, not about an import

Three sentences in `README.md` promise the file back — the opening paragraph's data-ownership
promise, the vendor-clouds bullet, and the *Dive-computer import* feature — and all three are
written as a claim about a file **you upload**, because that is the only path that stores one. A
logbook the converter reads is read once to produce DiveJSON and then discarded: the converter emits
no files at all, and the importer creates a stored-file row only for the app's own full-export
archive, which carries the binaries beside the document. So a diver who imports a zip of per-dive
FIT files gets every dive and none of the FITs.

**A file is kept on the recording it came from, not on the dive itself**, which is what the
*Dive-computer import* bullet now says: a dive holds one recording per device that recorded it, a
recording holds the files that produced it, and a diver wearing two computers — or uploading one
computer's JSON beside its FIT — gets a second recording or a second file rather than a replaced
one. A recording can also hold no files at all, which is what a converted logbook produces, so the
promise stays scoped to what you *upload*. The other two sentences keep their dive-level wording on
purpose: "a file you upload to a dive stays with it forever" is read by somebody who has met none of
this, and it is still true, a recording belonging to exactly one dive. The word earns its place
where the README is explaining the import itself, and nowhere else.

It is worth stating because the natural way to write any of the three is the sweeping way — "every
dive keeps the file it was imported from", which is what the opening paragraph said before the
converter shipped and read as true only while a bare file could not be a logbook. The *Logbook
import* bullet now says the asymmetry outright rather than leaving each of the three to imply it
away, and that is the sentence to correct first if the importer ever does store what it converted.

**The tagline dropped the promise rather than qualifying it.** `README.md`'s first line is a fourth
site, and the one place the qualifier does not fit: "the files you upload to a dive are kept" is
accurate and reads as a caveat, which is not what a stranger should meet first. The slot went to the
import side instead — "vendor exports in, open formats out" — which is true, is what this change
actually shipped, and leaves the kept-file detail to the two paragraphs below, where there is room
to say *which* files. The same sweep corrected *Self-hosting is a capability, not the product's
identity*, which listed the file promise among the things the software offers every diver wherever
it runs. That sentence is shared rather than local: `opendiving-web` carries it at its own
`README.md` and twice in the page metadata, so a replacement has to survive being adopted verbatim,
with nothing front-door-specific in it.

## The screenshots are copied from `opendiving-web`, never taken here

The four images in `docs/screenshots/` are byte-for-byte copies of the files of the same names in
[`opendiving-web`](https://github.com/opendiving/opendiving-web/tree/main/docs/screenshots). That
repository's `scripts/screenshots.mjs` generates them and, in the same shutter press, writes this
repository's copies too when a clone sits beside it — but it deliberately commits nothing in a
checkout it does not live in, so the commit is a separate act over here. Retaking an image therefore
means running the script next door and committing what lands, not photographing the app from this
side. There is nothing here that could: the app these are of is over there.

**That second write is the half that silently does not happen, so the copies drift.** The path it
uses defaults to a sibling of the web checkout, and a capture run from a worktree over there
resolves it to nothing — the script says so, writes only its own copies, and exits fine. Nothing on
this side notices: the README goes on rendering the older PNG, and the divergence is invisible until
somebody compares the files. `dashboard.png` sat a whole capture behind `opendiving-web` that way.
So mirroring is a comparison rather than a copy taken on trust. Read each blob out of
`opendiving-web`'s `origin/main` — `git show origin/main:docs/screenshots/<name>.png` — rather than
out of a working tree, which may be sitting on any branch at all, and hash both sides afterwards.

**All four are one product tour, from one account's logbook.** That is the invariant, and it is
about the *account* rather than the run: a retake against whatever account happened to have data in
it is how a README stitched from two different divers' logs gets in, which is the failure both
repositories are guarding against rather than one either has shipped. A change that moves fewer than
all of them is allowed exactly when the files it carries come across unchanged from a set already
shot against the same account as the ones staying put — a single new capture next door looks like
that from over here. A change that reaches *all* of them — a palette, a nav rewrite — is still a
single run of the script next door, so they cannot half-move.

**The row under `## Features` stacks rather than adding a third column, and it is levelled now.**
The dive shot is much the tallest image in the set, and a two-image row left a visible hole under
the short one beside it; a third image *beside* those two would only narrow all three. Stacking the
two short shots in the right cell fills that hole, and closing the remainder was deferred here for
as long as the height that would close it was unknown — it is set by the dive shot beside the pair,
and that shot was itself owed a retake.

**Both were taken together next door, which is why this repository's copies move in one commit.**
`opendiving-web` retook the dive shot and re-cut the gear frame against it in the same change, and
the row now reads level to within about 3 rendered px per edge at every container width from 480 up.
What changed is less the best case than the spread: the set committed here before ran 9.84 px per
edge at a 1012px container down to 2.70 at 480, so how level it looked depended on how wide the
reader's window was, and it is now 2.75 to 2.89 across that whole range — marginally larger at 480
than it was, and a third of what it was at 1012. The reasoning is `opendiving-web`'s `DECISIONS.md`,
under *The gear frame is the lever under the README row, and it has now been pulled* — including the
part that still governs this side: no single committed height is level for *every* reader, because
the stacked pair scales with the column while the leading between the two images does not, so
"levelled" means a residual small enough to stop reading as a defect rather than a zero.

None of that was or is this repository's to act on. Cropping an image here to even the row out would
break both the byte-for-byte copy and the rule behind it, and that stays true of a row that is level
— the next retake next door will move a height again, and the answer over here is still to copy what
lands rather than to compensate for it.

**So the row's markup encodes no image's height, and must not start to.** Every one of these is
retaken when the page behind it changes, and a retake moves heights — a dive page that gains a panel
is taller, a frame deliberately recut is shorter. A plain two-column table with a `<br>` between the
stacked pair survives all of that, because nothing in it is derived from a dimension. Markup tuned
to today's numbers would need re-tuning by whoever retakes an image next, and nothing in this
repository would tell them: there is no check here that can even open a PNG.

**The dive image's alt text is singular on purpose.** The app charts a profile per recording and
shows a switcher when a dive has more than one, but the dive in this set has a single recording, so
the caption says "its dive-computer recording" and promises no switcher. A dive with two charted
recordings is not reachable without shooting a different account, which the paragraph above rules
out. The caption is the half of this that drifts silently: it was rewritten to describe a recording
while the image still showed the pre-recordings page, and a picture disagreeing with its own caption
is invisible to every check in this repository.

## `## Features` describes the app, and is allowed to run ahead of the picture

The feature bullets and the screenshots answer the same question — what you get — and they move on
different clocks. Prose here is one edit; an image is a capture run next door, and the section above
is the whole story of why. When the app gains something the hero shot does not yet show, the prose
takes it first and the picture catches up later. The alternative is holding a true sentence back so
that it agrees with a stale PNG, which trades the thing a stranger actually reads for the thing they
glance at.

**That is not hypothetical, and the deco readouts are the worked example — now closed.** The profile
chart gained a panel under the depth plot carrying the readouts the computer itself computed —
no-deco time, time to surface, ppO₂, CNS and both gradient factors — and the recordings card gained
a line naming the mode the device ran in and the decompression model behind those numbers.
*Technical diving* and the opening paragraph said so for a while before any picture did, because the
retake was **held rather than merely outstanding**: `opendiving-web`'s `DECISIONS.md`, under *It
arrived without a retake, deliberately*, records a capture against a dive whose `gradient_factor`
series runs to five figures and reads as implausible across much of its length, and an open question
about what that field means on a Suunto. The chart drew the number the computer wrote and was right
to; a README hero was the wrong place to park the question.

**It settled, and the picture has caught up** — that is what the mirrored `dive-detail.png` above
carries. The axis that readout is drawn against is bounded now, so the retake shipped against the
same dive, and the committed image's chart legend names no-deco time, time to surface and both
gradient factors, with the deco ceiling still beside them.

**Four of the six, not six**, and the shortfall is the account's rather than the app's: that
recording carries no ppO₂ series and no CNS series, so the panel has nothing to draw for either.
(The *Exposure & Pressure* card in the same image does show a CNS figure; that is the dive's own
record, not a channel off the computer, and the two are not the same claim.) **The recordings card
shows neither half of the mode-and-model line**, for the same reason. It names the _device_ — Suunto
Ocean, with its serial and the diver's name for it — then the gradient factors and the firmware, and
its settings line reads a bare `GF 50/85`: next door, `decoModelLabel` prefixes those numbers with a
model name or an algorithm label whenever the recording carries one, so a bare pair is that field
being empty. So a sentence here may now claim the picture shows a readout, and must not claim it
shows all six, the mode, or a decompression model — the alt text stays as general as it is, which is
what keeps it true through the next retake.

Nothing here should ever be "fixed" to close a gap of this kind while one is open: cropping an image
would break the byte-for-byte copy the section above requires, and rolling the prose back to match
the PNG would make the README wrong about the app to make it agree with a photograph.

**Nothing catches this, in either direction.** These bullets describe a UI that lives in another
repository, no CI here reads them, and a PR next door cannot touch this file — the same
two-repository shape *The README names the import formats* records for the converter pin, with the
same fix: the change that ships the feature is not finished until a change here has named it. The
sweep that finds the stale sentences is a squeezed grep over every `*.md` here for the vocabulary of
a dive page — `profile`, `ceiling`, `CNS`, `OTU`, `deco`, `decompression`, `freedive`, `gauge` — run
against a newline-flattened file so that a sentence broken across two lines is still one string. Two
things about it are worth keeping: the enumerations are the hits that matter, because a list is what
goes short when the app grows, and the app's own spellings vary — `depth/temperature/tank-pressure`
in one sentence and `depth, temperature and tank pressure` in the next — so a pattern anchored on
one punctuation of it silently reports a clean repository.

## The test job's name is a contract, and two ordinary shapes would break it

`release-tooling.yml` runs the suite behind `scripts/release_version.py`, and the `main` ruleset on
this repository is to require that job as a status check. It requires `semantic-title` and
`shellcheck` today; `release-tooling` joins them when somebody with ruleset rights adds it. The name
it will be added under is the **job id**, because a job with no `name:` of its own reports under its
id — which is how both of the others are already named in that list.

Two shapes that look harmless would make the ruleset match nothing, and they fail identically and
silently: the pull request sits at "Expected — waiting for status" with no red X to explain it, for
good.

The first is a **matrix**. A matrix job's check run carries the matrix value in its name, so a job
with even a one-value matrix reports as `release-tooling (<value>)` and never as `release-tooling`.
`opendiving-web`'s `ci.yml` carries this scar in its own header: `lint-and-build` had a one-value
matrix expressing a variation that did not exist, and reported under a name no ruleset could ask
for.

The second is a **`paths:` filter**. A workflow filtered to `scripts/**` would not merely skip on a
docs-only pull request — it would produce no check run at all, and a required check with no run is
indistinguishable from one that has not started. Most traffic here is documentation, so that state
would be the normal state. `shellcheck.yml` reaches the same conclusion from the same direction and
says so in its own header.

Neither the job id nor the ruleset knows about the other. The ruleset lives in repository settings
and nothing in this tree references it, so renaming the job renames the check and nothing here
objects. If the job is ever renamed, the ruleset has to be edited in the same breath.

## The release tooling is standard library only, and reads each manifest the way its guard does

`scripts/release_version.py` imports nothing that is not in Python's standard library, and there is
no `pyproject.toml`, no lockfile and no install step — CI runs `python3 -m unittest` against the
runner's own interpreter.

The alternative was a test framework and a manifest to pin it in, which buys nicer test syntax and
costs: a dependency stream Renovate would raise pull requests for, a version to keep current, and an
install step on every docs-only pull request in a repository that ships no package and builds no
image. `.github/renovate.json5` describes what a dependency here even means, and a Python manifest
would quietly widen it.

The same restraint decides how the two manifests are **read**, and that one is not about weight at
all. `opendiving-api`'s `publish-image.yml` reads `pyproject.toml` with
`python3 -c 'import tomllib...'`; `opendiving-web`'s reads `package.json` with `node -p`. Each
compares its answer against the tag that has already been pushed, and refuses the build if the two
disagree. So this script reads both exactly the same way — `tomllib` for one, a `node -p`
subprocess for the other — and reads every file back through that same reader after writing it. A
second, different parser is a second answer waiting to happen, and the place it would surface is a
tag that cannot be deleted.

The cost is that `node` is a hard requirement of the test suite rather than an optional extra. It is
on every GitHub runner and on any machine that can work on `opendiving-web`, and a suite that
skipped itself when it was missing would report green for a script that cannot run.

## A version literal is found by where it sits, never by what its line says

`opendiving-web/package-lock.json` declares the project's own version twice — once in the root
object and once in `packages[""]` — and `packages[""]`'s line is **byte-identical** to
`node_modules/yocto-queue`'s, indentation included, because that dependency happens to be at
`0.1.0` too. A substitution anchored on the line's text rewrites both. `npm ci` does not object: it
tolerates a version that disagrees with `package.json`, and it certainly tolerates a dependency
whose declared version no longer matches the tarball URL and integrity hash sitting beside it. The
first sign of trouble is somebody installing, long after the tag went out.

So the two lock entries, `package.json`'s version, `pyproject.toml`'s `[project].version` and
`uv.lock`'s `[[package]] name = "opendiving-api"` block are all located by **position in the
document**: a path-aware JSON scan that reports byte offsets, and a TOML block scan that finds the
right `[[package]]` by its `name` among the hundred-odd others. `tomllib` and `json` cannot do this
job — they read and discard the offsets, and `tomllib` cannot write at all, while `json.dumps` over
`package.json` would reformat the entire file and fight both prettier and the lockfile.

Locating by position is an intention until something checks it, so the script checks itself: after
splicing, it compares the set of lines that actually changed against the set of lines the locators
said the literals were on, and refuses if they differ. A rewrite that changed the number of lines —
the shape a version with a stray newline takes — is refused by the same guard.

## What the version decision refuses, and the one thing it deliberately does not

The script proposes a number; it does not decide a release. Everything it refuses over is something
a person settles in a minute, and `--version` overrides the computation outright — which is the
honest answer to CONTRIBUTING.md's own rule that "breaking" is about the operator's experience
rather than the code's, and therefore not something any script can read off a commit log.

It refuses when the five version-bearing entries disagree, because there is then no current version
to bump from; when a repository's newest `vX.Y.Z` tag is not the version its manifests declare,
which is what a bump that merged with no tag pushed looks like, and bumping again from there would
skip a version nothing ever published; when a commit subject in the window is not a conventional
commit subject, since the alternative is silently reading it as a patch; and when nothing at all has
landed in any of the three repositories.

**An empty window in one repository is not a refusal**, and that is the deliberate departure. It is
the natural rule for a per-repository release tool and the wrong one here: three repositories carry
one number, so a repository with nothing to say still takes the product version. Refusing there
would mean a release in which `opendiving-api` reads `0.2.0` and `opendiving-web` reads `0.1.0` —
which the front door's guard would then refuse, correctly, after both images had been pushed.

## The labelling step retries, and "already exists" is not a failure

`.github/workflows/pr-title.yml` reads the repository's labels, creates the one it wants if that
read says it is missing, and then puts it on the PR. On 2026-09-13 that sequence failed a PR whose
title was perfectly good, and the job log is the whole argument for the shape the step has now:

```
HTTP 500 (https://api.github.com/graphql)
HTTP 500 (https://api.github.com/graphql)
label with name "feat" already exists; use `--force` to update its color and description
```

Two weaknesses compounded. The read was `mapfile -t existing < <(gh label list …)`, which cannot
fail: the non-zero status belongs to the process substitution, `mapfile` succeeds on the nothing it
was handed, and a repository whose labels could not be read comes out looking exactly like one that
has none. A flap on `api.github.com` was therefore reclassified, silently, as "`feat` does not
exist" — and the step went on to create a label this repository has carried since its first PR. The
create was the second weakness: `gh label create` exits non-zero on a name that is taken, the step
treated it as infallible, and `set -e` turned that into a red X on somebody's clean PR.

The fix is one small function and two rules about what counts as an error. `gh_retry` runs a `gh`
call up to three times with a widening pause, because GitHub's API bursts-fail and a single 500 is
rarely a fact about the repository. It takes a glob of *expected* non-zero output and returns on a
match rather than retrying, so "already exists" costs one call instead of three and fifteen seconds
of backoff; that arm has to be matched before the generic failure path, which would otherwise
swallow an expected state and call it a flap.

The first rule is that creating a label that already exists is not an error — it is the goal,
reached by somebody else. It happens for two ordinary reasons: a concurrent run of this same
workflow on another PR got there between this run's read and its create, or one of this call's own
earlier attempts landed and it was the *reply* that flapped. `--force` is not the answer to either,
because it would take a hand-tuned colour back off whoever tuned it.

The second is that a read or a write which genuinely fails all three attempts *is* an error, and
the job stops with an `::error::` quoting what gh actually said. Failing loudly is the point of the
exercise rather than a caveat to it, and the cost is quieter than "the PR falls out of the release
notes" — which it does not. `.github/release.yml` ends its categories with a `"*"` catch-all, so an
unlabelled PR is filed under *Other changes*: nothing is missing from the notes, a `feat:` is merely
absent from Features, and a section that is short reads as a section nobody had anything for. Both
reads are fatal on failure for that reason — including the read of the PR's *current* labels, where
the stake is the removals rather than the creates: an empty answer there leaves a retitled PR filed
under the type it used to have, which is the one thing the removal loop exists to stop. Either way
the wrong notes are generated weeks later by somebody who never saw this job, with nothing on screen
connecting the two.

This step is duplicated. Every repository that generates release notes from these labels runs its
own copy of it, and this fix landed in all of them together — which is the only reason this section
can be read as describing a solved problem. Nothing checks that the copies agree, so a later change
that lands in one and not the rest leaves the others with whatever this section is about. Diff the
labelling step across them before assuming otherwise.
