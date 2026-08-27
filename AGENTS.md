# opendiving

The install bundle and the operator documentation for OpenDiving. Three files an operator
downloads — `docker-compose.yml`, `Caddyfile`, `example.env` — plus `docs/`, plus the workflow that
publishes them as release assets.

`DECISIONS.md` records why things are the way they are, and is the file to read before changing
anything unfamiliar here — and to append to when you hit a new non-obvious choice.

## What is different about this repository

- **Nothing is built.** No code, no test suite, no lockfile, no image. The checks that exist are the
  PR-title workflow and whatever a human reads.
- **Nothing here reaches an existing install by merging.** The three files ship as **release
  assets**. A digest bumped on `main` is live only for someone who re-downloads
  `docker-compose.yml` after the next `vX.Y.Z` tag. Never write a comment or a doc line implying
  that a merge shipped something.
- **The audience is holding three files and no repository.** That is why the bundle carries comments
  far longer than code review would tolerate: an operator debugging at 1am has the file, not the
  git history and not this document. Explaining *why* a value is what it is, where they will read
  it, is the job.

## Rules

- **Cross-repository references are URLs, never relative paths.** Anything naming a file in
  `opendiving-api` or `opendiving-web` — in a doc, a comment, a compose annotation — is a full
  `https://github.com/opendiving/...` URL. A relative path dangles for everyone who cloned only one
  repository, which is everyone.
- **Never reference the umbrella's `plans/` directory.** Not from code, a comment, `DECISIONS.md`, a
  PR title or a PR body. Nobody who clones this repository has it. Write the reasoning out in
  `DECISIONS.md` instead of linking to the document it came from.
- **`example.env`, never `.env.example`.** GitHub renames a release asset whose name starts with a
  dot to `default.env.example`, the documented download URL 404s, and the workflow goes green
  anyway. Verified by uploading one. Do not "fix" the name.
- **The three third-party images stay digest-pinned** (`tag@sha256:...`). An operator pulls rather
  than builds, so a floating tag would hand them bytes this bundle was never tested against. This is
  the opposite of the deliberate float on `opendiving-api`'s Dockerfile base, and both are correct.
- **`docs/` is flat.** A `self-hosting/` subdirectory in a repository that is only self-hosting is a
  directory for nothing. The docs cross-link each other as siblings; keep it that way.
- Semantic **PR titles** — `<type>[(scope)][!]: <description>`, squash-merged, so the title becomes
  the subject on `main`. See `CONTRIBUTING.md`.

## There is no production

Nothing is hosted and nothing has ever been deployed. The local stack is the only deployment that
exists anywhere. No backward-compatibility hedges, no deprecation periods, no "apply this in
production too", no existing users. Breaking changes are fine.

The one thing that *is* real is the self-hoster who upgrades by pulling an image — which is why
releases, migrations-on-startup and the Breaking section of the notes are taken seriously while
none of the rest is.

## Verifying a change to the bundle

There is no CI that can tell you a compose file is right. What can be checked locally:

```bash
cp example.env .env && docker compose config >/dev/null && rm .env
```

`.env` has to exist for that to run at all — the services declare `env_file: .env`, and compose
refuses before it parses anything else — which is why the copy is part of the command rather than an
assumed prerequisite. It validates shape and interpolation and nothing else. A real change to the bundle — a new service, a changed
volume, a new required variable — is confirmed by installing it on a throwaway machine by following
`docs/install.md` verbatim, and every deviation you were tempted to make is a documentation bug.
