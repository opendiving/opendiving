# Contributing

This repository is the install bundle and the operator documentation — three files, the script that
downloads them, and a `docs/` directory — plus the release tooling under `scripts/`, which works out
what version the next release carries. No image is built here, so contributing is mostly prose and
YAML, with one shell script that `shellcheck` has an opinion about and one Python script with a test
suite behind it.

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
That is also why no release tool runs anywhere — semantic-release and release-please both compute a
version per repository from that repository's own commits, which drifts apart on the first api-only
fix and then has to be forced back by hand at every release afterwards.

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

Then, in order:

1. **Bump the manifests** in the two code repositories — `pyproject.toml` in api, `package.json` in
   web. One small PR each, titled `chore: release v0.4.0`. Nothing in *this* repository carries a
   version number, deliberately: see DECISIONS.md.

2. **Tag api and web** on their bump commits and push the tags. Each runs its own **Publish Image**,
   which builds amd64 and arm64 on native runners and pushes `0.4.0`, `0.4`, `latest` and
   `sha-<12>`. Watch both go green.

3. **Tag this repository last.**

   ```bash
   git tag v0.4.0 && git push origin v0.4.0
   ```

   **Release** then checks that `ghcr.io/opendiving/opendiving-api:0.4.0` and
   `ghcr.io/opendiving/opendiving-web:0.4.0` both exist and both carry both architectures, and
   refuses to publish anything if either is missing or half-published. This is the check that no
   per-repository workflow can make, and running it last is what makes it possible at all.

4. **Finish the draft.** The workflow opens a draft release with generated notes and the four
   install files attached. Write the headline paragraph and confirm the **Breaking** section — say
   "None" in so many words when it is empty, because generated notes simply omit an empty category
   and silence is not an answer somebody deciding whether to upgrade can use. Then publish.

**Recovery.** Nothing is published until step 3 passes, so a tag that fails its guard has cost
nothing: delete it, fix what was missing, re-cut it. A version tag that has been *published*, on the
other hand, is never repointed — a bad release gets a successor. `latest` and `X.Y` are moving
aliases and do get repointed, which is what makes a base-image CVE rebuild reach people.
