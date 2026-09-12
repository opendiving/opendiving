# Security Policy

OpenDiving is yours to self-host, and this repository is what you install: every instance run from
it is somebody's own server, holding their own dive log. Where that operator is not this project —
which is most instances — its maintainers have no access to the instance and no way to reach its
users, so a misconfigured deployment or a stale image on somebody's box is a report for whoever runs
that server. A defect in what we ship is ours, and it reaches every instance at once, so we would
much rather hear about one privately than read about it in a public issue.

**No running instance is a target for testing, and the one this project operates is not an
exception.** Test against a copy you run yourself and report what you find here; the code is what
this policy covers.

This project is [AGPL-3.0](LICENSE) and run by a single maintainer in their spare time. There is no
bug bounty and no money behind any of this — what we can offer is a prompt reply, a fix in the next
release, and credit in the release notes if you want it.

## Reporting a vulnerability

**Use GitHub's private vulnerability reporting:** the **Security** tab, then **Report a
vulnerability**. It opens a thread visible only to you and the maintainers, it keeps the whole
exchange attached to the repository, and it can become a published advisory with a CVE once the fix
is out.

If you have no GitHub account, or your report concerns a maintainer, **email
security@opendiving.app** instead.

Whatever you can tell us helps, but the four things that speed a fix up most are:

1. The version you found it on — the release tag, or the image digest.
2. What an attacker gets: someone else's dives, someone else's session, the whole database.
3. Enough to reproduce it.
4. Whether anyone else knows, and any disclosure timeline you have in mind.

## Which repository

This repository is the install bundle and the operator documentation. **A defect in the application
code belongs with the code**, and both component repositories have the same policy and the same
private-reporting tab:

- The API, the worker, authentication, the parsers, the admin panel —
  [opendiving-api](https://github.com/opendiving/opendiving-api/security).
- The web app, its route handlers, its headers —
  [opendiving-web](https://github.com/opendiving/opendiving-web/security).

Report it here if you aren't sure, or if it is the *combination* that is unsafe rather than either
half — that is exactly what this repository is responsible for. It will be moved if it belongs
elsewhere, and no report is lost by guessing wrong.

## Scope

**In scope** — a defect in what this repository ships:

- The install bundle — [`docker-compose.yml`](docker-compose.yml), [`Caddyfile`](Caddyfile),
  [`example.env`](example.env), [`install.sh`](install.sh) — and anything unsafe about the
  configuration a fresh install ends up with by following [docs/install.md](docs/install.md): a
  service exposed that shouldn't be, a default that is dangerous, a digest pinned to a
  known-vulnerable image. The script is its own case: it is downloaded and run before anything it
  installs exists, and it is what generates `SECRET_KEY` and the database password, so how it
  produces either — or anything it writes into `.env` that an operator would not expect — belongs
  here.
- Documentation that tells an operator to do something unsafe. A wrong instruction in
  [docs/](docs/) is a real vulnerability in a project whose whole install is people following it.

**Out of scope** — how a particular instance was set up. Self-hosting puts real security decisions
on the operator, and [docs/](docs/) is where they are documented:

- `TRUSTED_PROXY_IPS` naming the wrong network, so the API believes an `X-Forwarded-For` it
  shouldn't and every per-IP rate limit reads the wrong address.
- The admin panel reachable from the internet without `CRUD_ADMIN_ALLOWED_IPS`/`..._NETWORKS`, or
  with credentials someone can guess.
- A weak `POSTGRES_PASSWORD` or `SECRET_KEY`, a Postgres port published to the world, an
  unmaintained host, an out-of-date reverse proxy.

The line is whether the report describes something *we* can fix by changing a file in this
repository. A misconfiguration of your own instance is a support question — start with
[docs/troubleshooting.md](docs/troubleshooting.md) and open a normal issue if that doesn't get you
there.

## Supported versions

The latest release. A security fix lands on `main` and ships in the next one, and self-hosters pick
it up the way they pick up everything else:

```bash
docker compose pull && docker compose up -d
```

Migrations run themselves on startup, so upgrading is those two commands plus the release notes —
see [docs/upgrade.md](docs/upgrade.md). If you have pinned `OPENDIVING_VERSION`, move the pin.

A published version is never repointed, so a fix in our own code always arrives as a *new* version
number rather than as a rebuilt tag you might already be running. The single exception is a
vulnerability in a base image, republished at the existing tag precisely so that everyone following
`latest` or `X.Y` gets it. In that case `docker compose pull` is the whole fix even with a version
pinned.

A **digest** in `docker-compose.yml` is different: it ships as a release asset, so a bumped digest
reaches you on the next release and only if you re-download the file. That is the trade for a
compose file whose bytes are the ones we tested.
