# opendiving

This repository owns the install bundle, operator documentation and coordinated release tooling.
Application behavior belongs in [opendiving-web](https://github.com/opendiving/opendiving-web) or
[opendiving-api](https://github.com/opendiving/opendiving-api).

Read [CONTRIBUTING.md](CONTRIBUTING.md) before editing and the relevant sections of
[DECISIONS.md](DECISIONS.md). Preserve operator-facing comments that explain why a setting exists.
Configuration changes update the bundle, example environment and operator documentation together.
Identify companion application PRs and any manual upgrade steps in the PR description.

Verify bundle changes using CONTRIBUTING.md's install recipe. `docker compose config` checks shape
and interpolation; it does not establish that an installation works. Release changes follow the
coordinated release procedure rather than independent application version bumps.

For review fixes, inspect review bodies, inline comments and discussion attachments. Check that the
final diff, documentation and PR description agree, and state any unverified or blocked items.
Follow the repository's prose PR template and merge-queue policy.
