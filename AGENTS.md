# opendiving

The install bundle and the operator documentation for OpenDiving. Three files an operator
downloads — `docker-compose.yml`, `Caddyfile`, `example.env` — plus `install.sh`, which downloads
those three and writes the `.env`, plus `docs/`, plus the workflow that publishes all four as
release assets.

`DECISIONS.md` records why things are the way they are, and is the file to read before changing
anything unfamiliar here — and to append to when you hit a new non-obvious choice.

## What is different about this repository

- **Nothing is built.** No lockfile, no image, nothing compiled. `install.sh` is the only
  executable thing here, and the only automated check on it is `shellcheck` — there is no fixture
  for "a fresh VPS with Docker, a domain and a mail relay", so the rest is the PR-title workflow and
  whatever a human reads.
- **Nothing here reaches an existing install by merging.** The four files ship as **release
  assets**. A digest bumped on `main` is live only for someone who re-downloads
  `docker-compose.yml` after the next `vX.Y.Z` tag. Never write a comment or a doc line implying
  that a merge shipped something.
- **The audience is holding a few files and no repository.** That is why the bundle carries comments
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
- **`install.sh` edits `example.env`; it never writes a `.env` of its own.** The template is
  mostly comments, and those comments are the documentation the operator has afterwards. A
  generated twelve-line `.env` would throw away the most useful file in the bundle. Same rule for
  anything else that touches it: replace the value on a line, keep the line's neighbours.
- **`install.sh` starts nothing.** It prints `docker compose up -d` and stops. Caddy asks Let's
  Encrypt for a certificate the moment it comes up, and failed challenges are rate-limited per
  hostname per hour, so whether DNS is ready is the operator's call to make.
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

`install.sh` has two checks, and neither needs a release to exist. The linter, which is what CI
runs:

```bash
docker run --rm -v "$PWD:/mnt" koalaman/shellcheck:stable install.sh
```

And an actual install into a scratch directory. Run from a checkout the script installs the three
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
