# Contributing

This repository is the install bundle and the operator documentation — three files, the script that
downloads them, and a `docs/` directory — plus the release machinery: a script under `scripts/` that
works out what version the next release carries, and the workflow that cuts the release with it
across all three repositories. No image is built here, so contributing is mostly prose and YAML,
with one shell script that `shellcheck` has an opinion about and one Python script with a test suite
behind it.

The application lives in [opendiving-api](https://github.com/opendiving/opendiving-api) and
[opendiving-web](https://github.com/opendiving/opendiving-web), each with its own `CONTRIBUTING.md`
covering setup, checks and house rules. If your change is to the app, it belongs there.

Taking part here — an issue, a PR, a Discussions thread — means agreeing to the
[Code of Conduct](CODE_OF_CONDUCT.md). It is the Contributor Covenant, and reports go to
conduct@opendiving.app.

## What a change here looks like

- **The docs.** The bar is that an operator can follow them verbatim on a fresh machine. Every
  deviation you had to make on a real install is a documentation bug worth a PR.
- **The bundle.** `docker-compose.yml`, `Caddyfile` and `example.env` are what people download.
  They carry long comments on purpose: someone reading them has a few files, no repository and a
  problem. Explaining *why* a value is what it is where they will read it is the point, not clutter.
- **`install.sh`.** The same audience, and the same bar — it is downloaded and read before it is
  run. It edits `example.env` in place rather than writing a `.env` of its own, so the comments
  survive the install; it starts nothing. CI runs `shellcheck`, and
  `docker run --rm -v "$PWD:/mnt" koalaman/shellcheck:stable install.sh` runs the same check
  locally. *Verifying a change to the bundle* below has the end-to-end recipe, which works without a
  release existing.
- **The third-party digests.** postgres, redis and caddy are pinned `tag@sha256:...` because nothing
  here is built — an operator pulls, so a floating tag would hand them whatever upstream published
  today. Renovate raises a PR when one moves. Don't unpin them, and don't bump one by hand without
  saying what you tested it against.
- **`scripts/release_version.py`.** The version half of cutting a release: it reads the three
  repositories' commit windows since the last tag, proposes one product version, and writes that
  version into every manifest and lockfile entry that declares one in `opendiving-api` and
  `opendiving-web`. It refuses rather than guesses — a window it cannot classify, entries that
  disagree, a tag that is behind its manifest — and each refusal has a test. Standard library only:
  there is nothing to install and nothing to pin. `DECISIONS.md` has the reasoning behind all three
  of those choices.

Use semantic **PR titles** — `<type>[(scope)][!]: <description>`, where type is one of `feat`, `fix`,
`refactor`, `docs`, `test`, `chore`, `perf`, `ci`, `build`, `revert`. PRs are squash-merged, so the
title becomes the commit subject on `main` and is the only thing that outlives the branch.

## Verifying a change to the bundle

There is no CI that can tell you a compose file is right. What can be checked locally:

```bash
cp example.env .env && docker compose config >/dev/null && rm .env
```

`.env` has to exist for that to run at all — the services declare `env_file: .env`, and compose
refuses before it parses anything else — which is why the copy is part of the command rather than an
assumed prerequisite. It validates shape and interpolation and nothing else. A real change to the
bundle — a new service, a changed volume, a new required variable — is confirmed by installing it on
a throwaway machine by following `docs/install.md` verbatim, and every deviation you were tempted to
make is a documentation bug.

`install.sh` has two checks of its own, and neither needs a release to exist. The linter, which is
what CI runs:

```bash
docker run --rm -v "$PWD:/mnt" koalaman/shellcheck:stable install.sh
```

And an actual install into a scratch directory. Run from a checkout, the script installs the three
files sitting next to it instead of downloading a release — which is what makes a bundle change
testable before it is tagged — and every value it would ask for can be supplied in the environment,
so it needs no terminal either:

```bash
mkdir /tmp/od-test && cd /tmp/od-test
DOMAIN=dives.example.com SMTP_HOST=smtp.example.com SMTP_PORT=587 SMTP_USERNAME= \
  EMAIL_FROM_ADDRESS=noreply@example.com bash ~/path/to/opendiving/install.sh
diff <(sed 's/=.*//' ~/path/to/opendiving/example.env) <(sed 's/=.*//' .env)
docker compose config >/dev/null
```

That `diff` is the check worth keeping: line for line, the `.env` it writes has to be the template
with values replaced. Any difference at all means a comment went missing.

The release tooling has a real suite, and it is the other thing CI runs on every PR:

```bash
python3 -m unittest discover -s tests -t .
```

Run it from the repository root — `-t .` is what puts `scripts/` on the import path. It needs
Python 3.11 or newer for `tomllib`, and `node` on `PATH`: `package.json` is read here the way
`opendiving-web`'s publish workflow reads it, rather than by a second parser that could reach a
different answer. Nothing else is needed, and there is nothing to install.

## Retaking the README screenshots

The four images in `docs/screenshots/` are the README's product tour, and **nothing in this
repository can take them** — they are pictures of the web app, which lives next door. They are
byte-for-byte copies of the files of the same names in
[opendiving-web](https://github.com/opendiving/opendiving-web/tree/main/docs/screenshots), generated
by that repository's `scripts/screenshots.mjs`, and retaking one means running that script over
there and committing what it drops in here.

You need a clone of `opendiving-web`, a clone of
[opendiving-api](https://github.com/opendiving/opendiving-api), and a local stack: the API up with
`docker compose up` in the api clone, and the web dev server on `http://localhost:3000`. Then, from
the web clone:

```bash
npm run screenshots -- you@example.com             # all four
npm run screenshots -- you@example.com dashboard   # just the named ones
```

The account you name has to have a populated logbook behind it — enough dives to draw the dashboard
charts, one with a dive-computer recording, a gear item, and **a dive site with coordinates on it**.
Coordinates are the one hard requirement of the four: the site shot exists for its map, and the map
draws nothing for an unplaced site, so a logbook whose sites are all unplaced fails the run outright
rather than producing a poorer picture. Everything else is a preference the script ranks on — it
photographs the placed site with the most dives logged at it, and falls back to the first placed one
it finds. The script signs in as that account by requesting a magic link and reading the token back
out of the API container's log, which is why it only works against a local stack whose logs you can
read.

**How the copies reach this repository is one environment variable.** The script writes its own
`docs/screenshots/` and then writes this repository's, taking the path from `PRODUCT_DIR`, which
defaults to `../opendiving` relative to the web checkout — so a clone of this repository sitting
beside `opendiving-web` is picked up with nothing set. Anywhere else, name it:

```bash
PRODUCT_DIR=~/src/opendiving npm run screenshots -- you@example.com
```

With no clone at that path the script prints a note and writes only the web copies, which is what a
contributor with one checkout gets — not an error. It is also how the two repositories drift apart
without anyone noticing, so treat a mirror as a comparison against `opendiving-web`'s `main` rather
than as something the last run can be trusted to have done: hash the files on both sides.

**Committing them here is a second, manual step, and it is yours.** The script deliberately makes no
commit in a repository it does not live in, so after the run the new PNGs are sitting unstaged in
this checkout; the change lands as its own PR here, alongside the one next door. Take all four
together unless the images you are copying come across unchanged from a set already shot against the
same account: the invariant is that the tour is one logbook, and `DECISIONS.md` says what goes wrong
when it is not.

## Cutting a release

A release here is the **product's** release: the version both images are tagged with, plus the
files that install them. It is cut deliberately, never minted per merge — a version is an event
self-hosters read before they pull, and a stream of releases whose notes are one PR title each
trains people onto `latest`, the tag you least want somebody following.

Versions move in lockstep across all three repositories: one product version, so
`opendiving-api:0.4.0`, `opendiving-web:0.4.0` and release `v0.4.0` here are always a matched set.
That is also why the only release tool that runs is this repository's own — semantic-release and
release-please both compute a version per repository from that repository's own commits, which
drifts apart on the first api-only fix and then has to be forced back by hand at every release
afterwards. Neither is used here: one coordinator that reads all three windows and writes one
number is what replaces them.

**Pick the number** by looking at all three windows together:

| The window contains                                                                            | Pre-1.0 | From 1.0.0 |
| ---------------------------------------------------------------------------------------------- | ------- | ---------- |
| Anything breaking — a changed config or env contract, removed behaviour, a manual upgrade step | minor   | major      |
| Any user-visible feature                                                                       | minor   | minor      |
| Fixes and internals only                                                                       | patch   | patch      |

"Breaking" is about the operator's experience, not the code's — which is why a schema change on its
own is *not* breaking: migrations run themselves on startup. What counts is anything the operator has
to do by hand before the new version will run: an edited `.env`, a changed config contract, a removed
behaviour they depended on. **A change to the bundle that an existing install has to copy** — a new
required variable, a new service — is breaking in exactly this sense, because `docker compose pull`
does not update the compose file.

**Then run
[Cut the release](https://github.com/opendiving/opendiving/actions/workflows/release-cut.yml)** from
this repository's Actions tab, on `main`. It takes two boxes, both optional:

- **Version** — blank takes the number computed from the three commit windows; typing `0.4.0`
  overrules it. The table above is a judgement about the operator's experience and no script can
  make it, so the computed number is a proposal and this is how you decline it.
- **Dry run** — reports the version it would cut and the diff it would commit, and pushes nothing:
  no branch, no pull request, no tag and no release, in any of the three repositories.

One run does the rest. It opens a `chore(release): v0.4.0` pull request in `opendiving-api` and
`opendiving-web` writing the version into every manifest and lockfile entry that declares one, waits
for each repository's required checks, squash-merges both, tags the two commits that land, waits for
both **Publish Image** runs to publish `0.4.0`, `0.4`, `latest` and `sha-<12>` on amd64 and arm64,
and then tags this repository — which runs **Release**, the guard that checks
`ghcr.io/opendiving/opendiving-api:0.4.0` and `ghcr.io/opendiving/opendiving-web:0.4.0` both exist
with both architectures and refuses to publish anything if either is missing or half-published. That
is the check no per-repository workflow can make, and tagging here last is what makes it possible at
all.

Nothing in *this* repository carries a version number, deliberately: see DECISIONS.md. Its version
is the tag, which is why the coordinator writes to two repositories and tags three.

**Finish the draft.** The workflow leaves a draft release here with the four install files attached
and a body that opens by linking both component releases at this version, above the notes GitHub
generates from this repository's own pull requests. Those two links are built out of the version
rather than looked up, so one of them can land on a tag page rather than a release when that
repository's publish run is still queued — it catches up on its own, and there is nothing to fix
here. Write the headline paragraph and confirm the **Breaking** section — say "None" in so many words
when it is empty, because generated notes simply omit an empty category and silence is not an answer
somebody deciding whether to upgrade can use. Then publish.

**Nothing in api or web is bumped or tagged by hand** — the coordinator did both, and doing either
again is how the *next* release gets stuck rather than this one: the decision refuses when the
entries that declare a version disagree, or when a repository's newest tag is not what its manifests
say, and a hand bump or a stray tag produces exactly that. Each of them opens its own component
release off the tag it was given; whether that release arrives published or as a draft somebody
finishes is that repository's own business, and its releases page says which. Any instruction
anywhere to bump a manifest and push a `v` tag yourself describes the ritual this replaced.

**Recovery, and what the guard does not cover.** By the time this repository is tagged both images
are already out — `0.4.0`, `0.4`, `latest` and `sha-<12>` were pushed by each component's own
**Publish Image** run minutes earlier — so what the guard here protects is the product release and
the install assets, and not the images. If one repository's publish had failed while the other
succeeded, its `latest` has already moved and somebody pulling `latest` gets a mismatched pair. The
genuinely free-to-delete guard is the tag↔manifest check inside each `publish-image.yml`, which runs
before anything is built: a tag whose build failed there published nothing.

A tag that has published something is never repointed — a bad release gets a successor — and it
cannot be deleted either: the `tags` ruleset blocks deletion and force-pushes on `refs/tags/v*` for
everybody but an organisation admin, so re-cutting one is an owner's operation rather than a step in
this ritual. `latest` and `X.Y` are moving aliases and do get repointed, which is what makes a
base-image CVE rebuild reach people.

**If the run stops part-way it says so**, and writes the commands that finish the release by hand
into its job summary — the honest answer for a coordinator that cannot un-tag anything. Dispatching
it again is not the recovery: once either bump has merged, the version decision refuses, because the
entries that declare a version no longer agree. Read the summary and finish it.
