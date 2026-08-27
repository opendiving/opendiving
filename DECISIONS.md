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
