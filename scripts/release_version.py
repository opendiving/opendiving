#!/usr/bin/env python3
"""One product version for a lockstep release: decide it, then write it in.

`opendiving`, `opendiving-api` and `opendiving-web` release together — one number,
three tags, two images. This script is the half of that ritual a machine can be
trusted with: it reads the three commit windows since the last release, proposes a
version, and rewrites the files that declare it. Talking to GitHub is somebody else's
job, and deliberately not this file's.

    release_version.py decide  --product DIR --api DIR --web DIR [--version X.Y.Z]
    release_version.py rewrite --api DIR --web DIR --version X.Y.Z

`decide` prints a JSON object on stdout and a one-line summary on stderr. `rewrite`
edits four files in place and confirms each one by reading it back with the reader that
will read it next.

**It refuses rather than guesses.** A refusal exits **3** — argparse already owns 2 for
a usage error — and everything it refuses over is something a person settles in a
minute and a script cannot settle at all.
"""

import argparse
import json
import re
import subprocess
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


class Refusal(Exception):
    """Something a person has to settle. Printed, then exit 3."""


EXIT_REFUSED = 3


# --------------------------------------------------------------------------- #
# Versions
# --------------------------------------------------------------------------- #

# `re.fullmatch` and not a `$` anchor: `$` also matches before a trailing newline, so
# `"0.2.0\n"` would pass here and go on to be written into a manifest as two physical
# lines. That is not hypothetical - it is the regression the implementation this script
# is modelled on shipped, behind a tag that had already been pushed.
_VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
_VERSION_TAG = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")

Version = tuple[int, int, int]


def parse_version(text: str, where: str) -> Version:
    match = _VERSION.fullmatch(text)
    if match is None:
        raise Refusal(f"{where} is {text!r}, which is not an X.Y.Z version.")
    return (int(match[1]), int(match[2]), int(match[3]))


def format_version(version: Version) -> str:
    return "{}.{}.{}".format(*version)


# --------------------------------------------------------------------------- #
# What a commit window contains
# --------------------------------------------------------------------------- #

BREAKING = "breaking"
FEATURE = "feature"
ROUTINE = "routine"

_RANK = {ROUTINE: 0, FEATURE: 1, BREAKING: 2}

# The same list `.github/workflows/pr-title.yml` enforces on every pull request title,
# and the same list CONTRIBUTING.md spells out in prose. `tests/test_release_version.py`
# reads that workflow and fails if this drifts from it, because a type missing from here
# is not a parse error - it is a commit this script refuses to classify, on a release
# day, in a repository where every title had already passed its check.
COMMIT_TYPES = (
    "feat",
    "fix",
    "refactor",
    "docs",
    "test",
    "chore",
    "perf",
    "ci",
    "build",
    "revert",
)

_SUBJECT = re.compile(
    r"(?P<type>" + "|".join(COMMIT_TYPES) + r")"
    r"(?:\([a-z0-9._-]+\))?"
    r"(?P<breaking>!)?"
    r": .+"
)

# Conventional Commits' other way of saying it. `pr-title.yml` cannot see a body, so
# nothing in this project produces one of these today - honouring it costs a line and
# means a commit that says so in as many words is not read as a patch.
_BREAKING_FOOTER = re.compile(r"^BREAKING[ -]CHANGE:", re.MULTILINE)


def classify_commit(message: str) -> str | None:
    """One of BREAKING / FEATURE / ROUTINE, or None when the subject is not a
    conventional commit subject at all."""
    subject = message.strip().split("\n", 1)[0].strip()
    match = _SUBJECT.fullmatch(subject)
    if match is None:
        return None
    if match["breaking"] or _BREAKING_FOOTER.search(message):
        return BREAKING
    return FEATURE if match["type"] == "feat" else ROUTINE


def next_version(current: Version, level: str) -> Version:
    """CONTRIBUTING.md's *Pick the number* table, and nothing else.

    Pre-1.0 a breaking change buys a minor rather than a major, which is most of the
    point of being pre-1.0: the minors are the range that is allowed to break.
    """
    major, minor, patch = current
    if level == BREAKING:
        return (major + 1, 0, 0) if major >= 1 else (major, minor + 1, 0)
    if level == FEATURE:
        return (major, minor + 1, 0)
    return (major, minor, patch + 1)


# --------------------------------------------------------------------------- #
# git
# --------------------------------------------------------------------------- #


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise Refusal(f"`git {' '.join(args)}` failed in {repo}: {detail}")
    return proc.stdout


def version_tags(repo: Path) -> dict[Version, str]:
    """Every `vX.Y.Z` tag in the repository, by version.

    Tags under `v*` that are not `vX.Y.Z` - a pre-release, a typo - are ignored here for
    the same reason all three publish workflows refuse them: nothing downstream knows
    how to alias one.
    """
    found: dict[Version, str] = {}
    for line in _git(repo, "tag", "--list", "v*").splitlines():
        match = _VERSION_TAG.fullmatch(line.strip())
        if match is not None:
            found[(int(match[1]), int(match[2]), int(match[3]))] = line.strip()
    return found


def newest_version_tag(repo: Path) -> Version | None:
    tags = version_tags(repo)
    return max(tags) if tags else None


def commit_messages(repo: Path, base_tag: str) -> list[str]:
    """Every commit message in `base_tag..HEAD`, whole, bodies included.

    NUL-separated because a body is many lines and a subject is one of them; splitting
    this on newlines would read every bullet in a squash body as its own commit.
    """
    raw = _git(repo, "log", "--no-merges", "--format=%B%x00", f"{base_tag}..HEAD")
    return [chunk.strip() for chunk in raw.split("\0") if chunk.strip()]


# --------------------------------------------------------------------------- #
# Locating a version literal by its position in the document
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Span:
    """Half-open [start, end) over the *inner* characters of a quoted literal."""

    start: int
    end: int
    where: str


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


class _JsonScanner:
    """A path-aware scan of a JSON document that reports byte offsets.

    `json.loads` throws the offsets away, and the offsets are the whole point here:
    `package-lock.json`'s `packages[""]` version line is byte-identical to
    `node_modules/yocto-queue`'s today, so an edit anchored on the line's text rewrites
    both - leaving a dependency whose declared version no longer matches the tarball URL
    and integrity hash beside it, with `npm ci` staying perfectly green.
    """

    def __init__(self, text: str, where: str) -> None:
        self.t = text
        self.i = 0
        self.where = where
        self.hits: list[Span] = []

    def fail(self, message: str) -> None:
        raise Refusal(f"{self.where}: {message} at line {_line_of(self.t, self.i)}")

    def skip_ws(self) -> None:
        while self.i < len(self.t) and self.t[self.i] in " \t\r\n":
            self.i += 1

    def string(self) -> tuple[str, int, int]:
        start = self.i + 1
        i = start
        while True:
            if i >= len(self.t):
                self.i = i
                self.fail("unterminated string")
            char = self.t[i]
            if char == "\\":
                i += 2
                continue
            if char == '"':
                break
            i += 1
        self.i = i + 1
        return self.t[start:i], start, i

    def value(self, path: tuple[object, ...], target: tuple[object, ...]) -> None:
        self.skip_ws()
        if self.i >= len(self.t):
            self.fail("the document ends where a value was expected")
        char = self.t[self.i]
        if char == "{":
            self.obj(path, target)
        elif char == "[":
            self.arr(path, target)
        elif char == '"':
            _, start, end = self.string()
            if path == target:
                self.hits.append(Span(start, end, self.where))
        else:
            while self.i < len(self.t) and self.t[self.i] not in ",}] \t\r\n":
                self.i += 1
            if path == target:
                self.fail("the value at that path is not a string")

    def obj(self, path: tuple[object, ...], target: tuple[object, ...]) -> None:
        if path == target:
            self.fail("the value at that path is an object, not a string")
        self.i += 1
        self.skip_ws()
        if self.i < len(self.t) and self.t[self.i] == "}":
            self.i += 1
            return
        while True:
            self.skip_ws()
            if self.i >= len(self.t) or self.t[self.i] != '"':
                self.fail("expected an object key")
            raw, _, _ = self.string()
            self.skip_ws()
            if self.i >= len(self.t) or self.t[self.i] != ":":
                self.fail("expected ':' after an object key")
            self.i += 1
            self.value((*path, json.loads(f'"{raw}"')), target)
            self.skip_ws()
            if self.i >= len(self.t):
                self.fail("unterminated object")
            if self.t[self.i] == ",":
                self.i += 1
                continue
            if self.t[self.i] == "}":
                self.i += 1
                return
            self.fail("expected ',' or '}'")

    def arr(self, path: tuple[object, ...], target: tuple[object, ...]) -> None:
        if path == target:
            self.fail("the value at that path is an array, not a string")
        self.i += 1
        self.skip_ws()
        if self.i < len(self.t) and self.t[self.i] == "]":
            self.i += 1
            return
        index = 0
        while True:
            self.value((*path, index), target)
            self.skip_ws()
            if self.i >= len(self.t):
                self.fail("unterminated array")
            if self.t[self.i] == ",":
                self.i += 1
                index += 1
                continue
            if self.t[self.i] == "]":
                self.i += 1
                return
            self.fail("expected ',' or ']'")


def _render_path(path: tuple[object, ...]) -> str:
    return "".join(f"[{part!r}]" for part in path) or "the document root"


def locate_json_string(text: str, path: tuple[object, ...], where: str) -> Span:
    """The span of the string value at `path`, which must resolve exactly once."""
    scanner = _JsonScanner(text, where)
    scanner.value((), tuple(path))
    scanner.skip_ws()
    if scanner.i != len(text):
        scanner.fail("trailing content after the JSON document")
    if not scanner.hits:
        raise Refusal(f"{where}: nothing at {_render_path(tuple(path))}.")
    if len(scanner.hits) > 1:
        raise Refusal(f"{where}: {_render_path(tuple(path))} resolved more than once.")
    return scanner.hits[0]


# TOML gets a line scanner rather than a parser for the same reason JSON does: `tomllib`
# reads and cannot write, and the requirement is that everything except the literal come
# out byte-identical - so the edit has to know where the literal *is*, not merely what it
# says. Both files this touches are machine-adjacent and flat; a value split across lines
# or a `version` key inside a nested inline table would not be found, and not being found
# is a refusal rather than a wrong edit.
_TOML_HEADER = re.compile(r"\s*\[\[?(?P<name>[^\]]+)\]\]?\s*(#.*)?")
_TOML_STRING_KEY = re.compile(
    r'\s*(?P<key>[A-Za-z0-9_-]+)\s*=\s*"(?P<value>[^"\\]*)"\s*(#.*)?'
)

TomlBlock = tuple[str, list[tuple[str, int]]]


def _toml_blocks(text: str) -> list[TomlBlock]:
    """(header, [(line, that line's offset)]) for each table in the file.

    The first block's header is "" - the file's implicit root table.
    """
    blocks: list[TomlBlock] = [("", [])]
    offset = 0
    for line in text.split("\n"):
        header = _TOML_HEADER.fullmatch(line)
        if header is not None:
            blocks.append((header["name"].strip(), []))
        else:
            blocks[-1][1].append((line, offset))
        offset += len(line) + 1
    return blocks


def _toml_string_keys(block: list[tuple[str, int]], key: str) -> list[tuple[str, Span]]:
    found = []
    for line, offset in block:
        match = _TOML_STRING_KEY.fullmatch(line)
        if match is not None and match["key"] == key:
            found.append(
                (
                    match["value"],
                    Span(offset + match.start("value"), offset + match.end("value"), key),
                )
            )
    return found


def _one_key_span(block: list[tuple[str, int]], key: str, where: str) -> Span:
    found = _toml_string_keys(block, key)
    if not found:
        raise Refusal(f'{where}: no `{key} = "..."` line.')
    if len(found) > 1:
        raise Refusal(f"{where}: `{key}` is assigned more than once.")
    span = found[0][1]
    return Span(span.start, span.end, where)


def locate_toml_table_key(text: str, table: str, key: str, where: str) -> Span:
    """The span of `key`'s quoted value inside the `[table]` table."""
    matches = [block for header, block in _toml_blocks(text) if header == table]
    if not matches:
        raise Refusal(f"{where}: no `[{table}]` table.")
    if len(matches) > 1:
        raise Refusal(f"{where}: `[{table}]` appears more than once.")
    return _one_key_span(matches[0], key, where)


def locate_uv_lock_package_version(text: str, package: str, where: str) -> Span:
    """The span of the `version` of the `[[package]]` block naming `package`.

    Not "the `version` line after the `name` line": the lock carries a hundred-odd of
    these blocks and the project's own is one of them, so the block is found by its name
    and only then is the line found inside it.
    """
    wanted = [
        block
        for header, block in _toml_blocks(text)
        if header == "package"
        and [value for value, _ in _toml_string_keys(block, "name")] == [package]
    ]
    if not wanted:
        raise Refusal(f"{where}: no `[[package]]` block named {package!r}.")
    if len(wanted) > 1:
        raise Refusal(f"{where}: more than one `[[package]]` block names {package!r}.")
    return _one_key_span(wanted[0], "version", where)


# --------------------------------------------------------------------------- #
# Reading a version back the way the thing downstream will read it
# --------------------------------------------------------------------------- #


def read_pyproject_version(api: Path) -> str:
    """`opendiving-api`'s `publish-image.yml` reads it exactly this way and compares the
    answer against the pushed tag before it builds anything. A second, different reader
    here is a second answer waiting to happen."""
    path = api / "pyproject.toml"
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    value = data.get("project", {}).get("version")
    if not isinstance(value, str):
        raise Refusal(f"{path} has no [project].version string.")
    return value


def read_uv_lock_version(api: Path, package: str = "opendiving-api") -> str:
    """`uv sync --locked` in api's Dockerfile refuses a lock that disagrees with
    `pyproject.toml`, and that build is api's required `runtime-imports` check - so a
    bump that writes the manifest alone opens a pull request that can never merge."""
    path = api / "uv.lock"
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    entries = [
        entry for entry in data.get("package", []) if entry.get("name") == package
    ]
    if len(entries) != 1:
        raise Refusal(f"{path}: expected exactly one package named {package!r}.")
    value = entries[0].get("version")
    if not isinstance(value, str):
        raise Refusal(f"{path}: {package} has no version string.")
    return value


def read_package_json_version(web: Path) -> str:
    """`opendiving-web`'s `publish-image.yml` reads it with `node -p`, so this does too,
    and with the runner's own node rather than a pinned one for the same reason.

    `JSON.stringify` rather than the bare value: it makes whitespace visible, so a
    version that picked up a stray newline comes back as a different string here instead
    of being normalised away by a `.strip()` on this side.
    """
    proc = subprocess.run(
        ["node", "-p", "JSON.stringify(require('./package.json').version)"],
        cwd=str(web),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise Refusal(f"reading {web / 'package.json'} with node failed: {detail}")
    try:
        value = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise Refusal(
            f"{web / 'package.json'}: node answered {proc.stdout.strip()!r}, which is "
            "not a version."
        ) from exc
    if not isinstance(value, str):
        raise Refusal(f"{web / 'package.json'}: version is not a string.")
    return value


def read_package_lock_versions(web: Path) -> tuple[str, str]:
    """The lock's two declarations of the project's own version: root, then `packages[""]`.

    `npm ci` tolerates these disagreeing with `package.json`, which is exactly what makes
    them worth reading here - the drift is silent everywhere else.
    """
    path = web / "package-lock.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    try:
        root = data["version"]
        own = data["packages"][""]["version"]
    except (KeyError, TypeError) as exc:
        raise Refusal(f"{path} is missing a project version entry.") from exc
    if not isinstance(root, str) or not isinstance(own, str):
        raise Refusal(f"{path}: a project version entry is not a string.")
    return root, own


# --------------------------------------------------------------------------- #
# The current state of the two manifests, and what it has to agree about
# --------------------------------------------------------------------------- #


def declared_versions(api: Path, web: Path) -> dict[str, str]:
    """Every entry of the structural kind, and what each of them says right now."""
    lock_root, lock_own = read_package_lock_versions(web)
    return {
        "opendiving-api/pyproject.toml [project].version": read_pyproject_version(api),
        'opendiving-api/uv.lock [[package]] "opendiving-api"': read_uv_lock_version(api),
        "opendiving-web/package.json .version": read_package_json_version(web),
        "opendiving-web/package-lock.json .version": lock_root,
        'opendiving-web/package-lock.json .packages[""].version': lock_own,
    }


def current_product_version(api: Path, web: Path) -> Version:
    """The one version api and web both declare, or a refusal naming the disagreement.

    Five entries declare it between them and every pair of them can drift. Only one of
    those drifts is loud: `uv.lock` against `pyproject.toml` fails api's required
    `runtime-imports` check. The rest are silent, which is why they are read here rather
    than trusted.
    """
    declarations = declared_versions(api, web)
    versions = {
        where: parse_version(value, where) for where, value in declarations.items()
    }
    distinct = set(versions.values())
    if len(distinct) > 1:
        listed = "\n".join(
            f"  {where}: {value}" for where, value in declarations.items()
        )
        raise Refusal(
            "The version-bearing entries do not agree, so there is no current product "
            f"version to bump:\n{listed}\n"
            "Put them back in step in their own pull request first."
        )
    return distinct.pop()


# --------------------------------------------------------------------------- #
# decide
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Window:
    repo: str
    base_tag: str
    messages: list[str]


def read_windows(repos: dict[str, Path], current: Version) -> list[Window]:
    """Each repository's commits since the tag the last release was cut at.

    The base is `v<current>` in all three rather than each repository's own newest tag,
    and the check below is what earns that: a repository whose newest tag is behind its
    manifest is one where a bump merged and the tag push did not land - the worst
    incident on record for the implementation this is modelled on - and bumping again
    from there skips a version that nothing ever published.
    """
    base = f"v{format_version(current)}"
    windows = []
    for name, path in repos.items():
        newest = newest_version_tag(path)
        if newest is None:
            raise Refusal(
                f"{name} carries no vX.Y.Z tag, so there is no window to read. "
                "A first release is cut by hand."
            )
        if newest != current:
            raise Refusal(
                f"{name}'s newest tag is v{format_version(newest)} but the manifests "
                f"read {format_version(current)}. Either a bump merged without its tag "
                "being pushed, or a tag was pushed without its bump. Finish that "
                "release before cutting another."
            )
        windows.append(Window(name, base, commit_messages(path, base)))
    return windows


def tally(windows: list[Window]) -> tuple[dict[str, dict[str, int]], list[str]]:
    """Per-repository counts, plus the subjects that could not be classified at all."""
    counts: dict[str, dict[str, int]] = {}
    unclassified: list[str] = []
    for window in windows:
        seen = {BREAKING: 0, FEATURE: 0, ROUTINE: 0, "unclassified": 0}
        for message in window.messages:
            kind = classify_commit(message)
            if kind is None:
                seen["unclassified"] += 1
                unclassified.append(f"  {window.repo}: {message.splitlines()[0]}")
            else:
                seen[kind] += 1
        counts[window.repo] = {"commits": len(window.messages), **seen}
    return counts, unclassified


def decide_level(counts: dict[str, dict[str, int]]) -> str:
    """The highest level any of the three windows justifies, judged jointly.

    An empty window is not an error here, and this is the one place this deliberately
    does the opposite of the implementation it is modelled on. Under lockstep a
    repository with nothing in its window still takes the product version, because the
    alternative is two repositories carrying different numbers for one release.
    """
    level = ROUTINE
    for seen in counts.values():
        for kind in (BREAKING, FEATURE):
            if seen[kind] and _RANK[kind] > _RANK[level]:
                level = kind
    return level


def decide(repos: dict[str, Path], explicit: str | None) -> dict[str, object]:
    current = current_product_version(repos["opendiving-api"], repos["opendiving-web"])
    windows = read_windows(repos, current)
    counts, unclassified = tally(windows)

    if explicit is not None:
        chosen = parse_version(explicit, "--version")
        level: str | None = None
        if chosen <= current:
            raise Refusal(
                f"--version {explicit} does not come after the current "
                f"{format_version(current)}. A release never goes backwards, and "
                "re-cutting a published version is not something this can do."
            )
    else:
        if unclassified:
            listed = "\n".join(unclassified)
            raise Refusal(
                "These commits are not conventional commit subjects, so the window "
                f"cannot be classified:\n{listed}\n"
                "Pass --version to name the number yourself."
            )
        if not any(seen["commits"] for seen in counts.values()):
            raise Refusal(
                "Nothing has landed in any of the three repositories since "
                f"{windows[0].base_tag}. There is no release to cut; pass --version if "
                "you mean to cut one anyway."
            )
        level = decide_level(counts)
        chosen = next_version(current, level)

    return {
        "current": format_version(current),
        "version": format_version(chosen),
        "level": level,
        "source": "explicit" if explicit is not None else "computed",
        "base_tag": windows[0].base_tag,
        "windows": counts,
    }


# --------------------------------------------------------------------------- #
# rewrite
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Site:
    """One place a repository declares its own version."""

    path: Path
    where: str
    locate: Callable[[str, str], Span]


def sites(api: Path, web: Path) -> list[Site]:
    """Every entry of the structural kind this script rewrites, and no others.

    The set is what it is because a sweep for the literal returns far more: dependency
    specifiers like `ruff>=0.1.0` that mean something else entirely, unrelated
    `package-lock.json` entries that happen to share the digits, prose in CONTRIBUTING.md
    and DECISIONS.md, comments in workflows, and a UDDF test fixture whose `<version>`
    records the *generator's* version and legitimately reads the same number. A
    declaration is a tracked manifest or lockfile entry naming this project; everything
    else that sweep returns is out of scope by construction, and rewriting any of it is
    a corruption rather than a bump.
    """
    return [
        Site(
            api / "pyproject.toml",
            "opendiving-api/pyproject.toml [project].version",
            lambda text, where: locate_toml_table_key(text, "project", "version", where),
        ),
        Site(
            api / "uv.lock",
            'opendiving-api/uv.lock [[package]] "opendiving-api" version',
            lambda text, where: locate_uv_lock_package_version(
                text, "opendiving-api", where
            ),
        ),
        Site(
            web / "package.json",
            "opendiving-web/package.json .version",
            lambda text, where: locate_json_string(text, ("version",), where),
        ),
        Site(
            web / "package-lock.json",
            "opendiving-web/package-lock.json .version",
            lambda text, where: locate_json_string(text, ("version",), where),
        ),
        Site(
            web / "package-lock.json",
            'opendiving-web/package-lock.json .packages[""].version',
            lambda text, where: locate_json_string(
                text, ("packages", "", "version"), where
            ),
        ),
    ]


def changed_line_numbers(before: str, after: str, where: str) -> set[int]:
    """Which lines differ, refusing outright if the line count moved.

    The line count moving is the shape worth catching on its own: a version that picked
    up a newline writes itself into a manifest as two physical lines and leaves a
    package that does not import.
    """
    old, new = before.split("\n"), after.split("\n")
    if len(old) != len(new):
        raise Refusal(
            f"{where}: the rewrite changed the number of lines "
            f"({len(old)} -> {len(new)}), which a version literal cannot do."
        )
    return {
        index + 1 for index, (a, b) in enumerate(zip(old, new, strict=True)) if a != b
    }


def plan_file(path: Path, group: list[Site], old: str, new: str) -> tuple[str, list[int]]:
    """What this one file should become, and which lines that moves.

    Everything except the literal has to come out byte-identical, and the check for that
    is the line set rather than a claim about the splice: `changed` is measured from the
    two texts, `expected` from where the locators said the literals were, and the two
    having to agree is what turns "anchored on position" from an intention into a test
    the script runs on itself every time.
    """
    before = path.read_text(encoding="utf-8")
    spans = []
    for site in group:
        span = site.locate(before, site.where)
        found = before[span.start : span.end]
        if found != old:
            raise Refusal(
                f"{site.where} reads {found!r}, not the expected {old!r}. "
                "Something moved underneath this run."
            )
        spans.append(span)

    after = before
    for span in sorted(spans, key=lambda s: s.start, reverse=True):
        after = after[: span.start] + new + after[span.end :]

    expected = {_line_of(before, span.start) for span in spans}
    changed = changed_line_numbers(before, after, str(path))
    if changed != expected:
        raise Refusal(
            f"{path}: the rewrite touched lines {sorted(changed)} but should have "
            f"touched only {sorted(expected)}."
        )
    return after, sorted(expected)


def rewrite(api: Path, web: Path, target: str) -> list[tuple[str, int]]:
    """Write `target` into every declaration, then read every one of them back.

    Every file is located, spliced and checked before any of them is written, so a
    refusal on the fourth leaves the first three as it found them. A half-rewritten pair
    of repositories is the one outcome nothing downstream can report honestly: it
    survives `npm ci`, and api's lock check would call it a manifest mismatch rather
    than a failed release.

    The read-back at the end is not belt and braces. The string written here is what
    `publish-image.yml` compares the pushed tag against, and the tag goes out before
    anything is built - so a rewrite that went wrong is otherwise discovered by a build
    that cannot be un-tagged.
    """
    chosen = parse_version(target, "--version")
    current = current_product_version(api, web)
    if chosen <= current:
        raise Refusal(
            f"--version {target} does not come after the current "
            f"{format_version(current)}."
        )

    old, new = format_version(current), format_version(chosen)
    all_sites = sites(api, web)
    planned: list[tuple[Path, str, list[int]]] = []
    for path in dict.fromkeys(site.path for site in all_sites):
        group = [site for site in all_sites if site.path == path]
        after, lines = plan_file(path, group, old, new)
        planned.append((path, after, lines))

    written: list[tuple[str, int]] = []
    for path, after, lines in planned:
        path.write_text(after, encoding="utf-8")
        written.extend((str(path), line) for line in lines)

    confirmed = current_product_version(api, web)
    if confirmed != chosen:
        raise Refusal(
            f"after rewriting, the entries read {format_version(confirmed)} rather "
            f"than {new}."
        )
    return written


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    sub = parser.add_subparsers(dest="command", required=True)

    proposal = (
        "cut this version instead of the computed one. Breaking is about the operator's "
        "experience rather than the code's, which no script can decide, so the computed "
        "number is a proposal."
    )

    decide_parser = sub.add_parser(
        "decide", help="propose one product version for all three repositories"
    )
    decide_parser.add_argument("--product", required=True, type=Path)
    decide_parser.add_argument("--api", required=True, type=Path)
    decide_parser.add_argument("--web", required=True, type=Path)
    decide_parser.add_argument("--version", help=proposal)

    rewrite_parser = sub.add_parser(
        "rewrite", help="write a version into every entry that declares one"
    )
    rewrite_parser.add_argument("--api", required=True, type=Path)
    rewrite_parser.add_argument("--web", required=True, type=Path)
    rewrite_parser.add_argument("--version", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "decide":
            decision = decide(
                {
                    "opendiving": args.product,
                    "opendiving-api": args.api,
                    "opendiving-web": args.web,
                },
                args.version,
            )
            print(json.dumps(decision, indent=2))
            detail = decision["source"]
            if decision["level"]:
                detail = f"{detail}, {decision['level']}"
            print(
                f"{decision['current']} -> {decision['version']} ({detail})",
                file=sys.stderr,
            )
        else:
            for path, line in rewrite(args.api, args.web, args.version):
                print(f"{path}:{line} -> {args.version}", file=sys.stderr)
    except Refusal as refusal:
        print(f"error: {refusal}", file=sys.stderr)
        return EXIT_REFUSED
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
