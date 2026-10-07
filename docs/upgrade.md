# Upgrade

```bash
cd /path/to/opendiving
docker compose pull
docker compose up -d
```

That is the whole procedure, unless a release's notes name a step of their own —
[below](#read-the-release-notes) says which two kinds there are. Database migrations run themselves:
the API executes `alembic upgrade head` as it starts, under an advisory lock so the four workers in
the container cannot race each other, and only then begins serving. A schema change is therefore not
a manual step and never has been one for an installed instance.

Take a backup first anyway — [backup-restore.md](backup-restore.md), the database dump *and* the
uploaded files, since neither is a backup without the other — because going back is never
automatic.

## Read the release notes

Releases are cut deliberately, not per merge, and each one carries an explicit **Breaking** section
that says "None" in so many words when there is nothing. Breaking here means something *you* have to
do: an edited `.env`, a changed configuration contract, a removed behaviour, a command to run once
the new version is up. A schema change on its own is not breaking, because it applies itself.

<https://github.com/opendiving/opendiving/releases>

**What changed in the app itself is one link further on.** A release here is the install bundle and
this documentation; the API and the web app are released in their own repositories at the same
version, and a release here opens by linking both. Follow those for the features and fixes — a
release on this page whose own list is all install files and CI is an ordinary release, not an empty
one.

**`docker compose pull` updates images and nothing else.** `docker-compose.yml`, `Caddyfile` and the
`.env` you made from `example.env` are files you downloaded once; they stay exactly as they are
through every upgrade. So when a release's Breaking section names one of them, re-downloading it is
the manual step, and it is one of the two kinds of manual step this project's releases have:

```bash
curl -LO https://github.com/opendiving/opendiving/releases/latest/download/Caddyfile
```

Your `.env` is never overwritten — take new settings out of that release's `example.env` by hand,
which is also how you get the paragraph explaining each one.

**The other kind is a backfill**, a command run once in the api container after the upgrade to bring
data the previous version stored level with what the new one would store. The one a Breaking section
names is the profile backfill. Each dive's per-sample profile is read out of the dive-computer files
you uploaded, and a stored profile records which reader read it. When a release changes how that
reading is done, its Breaking section names the backfill, with the exact command — this one, plus
any flags that release needs:

```bash
docker compose exec api python -m src.scripts.backfill_dive_profiles
```

It re-reads each file-backed profile from its stored files, and running it twice is harmless: the
second run finds nothing left to do. `--dry-run` reports what it would re-read and writes nothing.
Until it runs, every profile is served as the previous reader left it — a valid profile, charted as
before — so the instance is usable in between. A release that only moves the version of
[`divejson`](https://github.com/divejson/divejson-py), the package that reads every dive-computer
file, also leaves the stored profiles behind the new reader, and just as valid; there the backfill
is optional — run it when convenient to bring them level — and not a Breaking step.

**The species photo re-check is a backfill of that optional sort**, and the release notes name it
outside Breaking. A species photo narrower than 500 px is refused rather than stored soft, and this
brings the photos stored before that rule under it:

```bash
docker compose exec api python -m src.scripts.backfill_species_photos --recheck-size --dry-run
docker compose exec api python -m src.scripts.backfill_species_photos --recheck-size
```

It reads each stored photo's own bytes and calls Wikimedia Commons for nothing. It records every
photo's width and height, and drops one narrower than 500 px unless an admin pinned it — and any
whose stored file is missing or will not open, pinned or not. The dry run lists what it would drop
and ends `without_dimensions=N to_drop=M`; the real run ends `without_dimensions=N dropped=M`, and a
dry run after it reports zero for both. Running it twice is harmless. Until it runs, a narrow photo
is served exactly as before; once it has, a dive page that was showing a dropped photo can show a
broken image for up to an hour, until its cached copy expires.

## Cards and page heads need the map renderer

From the release after 0.3.0, the maps behind the dive, trip and dive site cards, and at the head of
a dive's, a trip's and a dive site's own page, are drawn by this stack rather than by the browser —
by a `map-renderer` service that is off unless you switch it on. Upgrade without it and every card
and every page head shows water where its map was: nothing draws a page head's map in the browser
any more. Switching it on is three steps, because the service is defined in a file you
downloaded once:

```bash
curl -LO https://github.com/opendiving/opendiving/releases/latest/download/docker-compose.yml
```

then the two lines in `.env` that [configuration.md](configuration.md#the-map-renderer) gives —
`map-renderer` added to `COMPOSE_PROFILES`, and `MAP_RENDERER_URL=map-renderer:3000` — and
`docker compose up -d`. A stretch of coast is drawn the first time any card or page head shows it
after that, and stored for everybody. Leaving it off is a supported choice too, and the lighter one:
the renderer adds roughly 210 MB of memory at its peak.

## Pin the version

`OPENDIVING_VERSION` in `.env` selects the tag both images run, and it defaults to `latest`. Once
this instance holds dives you'd miss, pin it:

```bash
OPENDIVING_VERSION=0.4.0
```

Upgrading is then editing that line and running the two commands above. The api and web images
always carry the same version number — they are released together, and mixing them is not a
supported configuration.

Available tags for a released version `X.Y.Z`: `X.Y.Z` (exact), `X.Y` (patches only), `latest`, and
`sha-<12>`. A bare major (`1`, `2`, …) appears from 1.0.0 onwards; below it there is deliberately no
`0` alias, because "any 0.x" is exactly the range whose minor versions are allowed to break.

## Downgrades are not supported

Same stance as Immich, and for the same reason: migrations move forward only. There is no
`alembic downgrade` path maintained across releases, and a newer schema handed to an older image
fails in whatever way that image happens to fail.

Rolling back means restoring the backup you took before upgrading, into the version you took it
from. That is what makes the first line of this page a real instruction rather than a formality.

## Upgrading the database itself

Postgres major versions are pinned in the compose file and move only when a release says so — the
data directory is version-specific, and a new major cannot read the old one's files in place. When
one comes, its release notes carry the procedure. Until then, `docker compose pull` never changes
your Postgres major underneath you: every third-party image in the bundle is pinned to a digest, not
just a tag.

## If something goes wrong

`docker compose logs api` is where a failed migration reports, with the revision it stopped on. The
container exits rather than serving against a schema it doesn't match, which is the intended
behaviour: a half-migrated database that is up and answering is worse. Restore the backup, pin
`OPENDIVING_VERSION` back to what you were running, and open an issue with the log — a migration
that fails on a real installation is a bug in the release, not in your instance.
