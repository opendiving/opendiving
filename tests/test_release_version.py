"""Tests for `scripts/release_version.py`.

The fixtures below are miniatures of the real files rather than copies of them: this
repository has no checkout of `opendiving-api` or `opendiving-web` and CI has no way to
get one, so the hazards are reproduced here instead. Each miniature keeps the shape that
makes its file dangerous - the collision between `packages[""]`'s version line and a
dependency's, the hundred-odd `[[package]]` blocks the project's own sits among, the
`target-version` key that is not a version - and nothing else.

`python3 -m unittest discover -s tests -t .` from the repository root. `node` has to be
on PATH: `package.json` is read here the way `opendiving-web`'s publish workflow reads
it, and a test that quietly skipped itself over a missing interpreter would report a
green suite for a script that cannot run.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts import release_version as rv

REPO_ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# Miniatures of the four files this script rewrites
# --------------------------------------------------------------------------- #

PYPROJECT = """\
[project]
name = "opendiving-api"
version = "0.1.0"
requires-python = "~=3.14.0"
dependencies = [
    "fastapi>=0.109.1",
    "ruff>=0.1.0",
]

[tool.ruff]
target-version = "py314"

[tool.mypy]
python_version = "3.14"
"""

# Two `version = "0.1.0"` lines, and only one of them is the project's. The block is
# found by its `name`, never by being the first or the last.
UV_LOCK = """\
version = 1
requires-python = "==3.14.*"

[[package]]
name = "alembic"
version = "0.1.0"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "opendiving-api"
version = "0.1.0"
source = { editable = "." }
dependencies = [
    { name = "alembic" },
]

[package.metadata]
requires-dist = [
    { name = "alembic", specifier = ">=1.16.0" },
    { name = "ruff", marker = "extra == 'dev'", specifier = ">=0.1.0" },
]

[[package]]
name = "ruff"
version = "0.14.2"
source = { registry = "https://pypi.org/simple" }
"""

PACKAGE_JSON = """\
{
  "name": "opendiving-web",
  "version": "0.1.0",
  "private": true,
  "dependencies": {
    "p-limit": "^3.1.0"
  }
}
"""

# The sharp one. `packages[""]`'s version line and `node_modules/yocto-queue`'s are
# byte-identical, down to the indentation, exactly as they are in the real lockfile.
# An edit anchored on the line's text rewrites both, `npm ci` stays green, and the
# dependency is left declaring a version its tarball URL and integrity hash disagree
# with - behind a tag that has already been pushed.
PACKAGE_LOCK = """\
{
  "name": "opendiving-web",
  "version": "0.1.0",
  "lockfileVersion": 3,
  "requires": true,
  "packages": {
    "": {
      "name": "opendiving-web",
      "version": "0.1.0",
      "dependencies": {
        "p-limit": "^3.1.0"
      }
    },
    "node_modules/p-limit": {
      "version": "3.1.0",
      "resolved": "https://registry.npmjs.org/p-limit/-/p-limit-3.1.0.tgz",
      "dependencies": {
        "yocto-queue": "^0.1.0"
      }
    },
    "node_modules/yocto-queue": {
      "version": "0.1.0",
      "resolved": "https://registry.npmjs.org/yocto-queue/-/yocto-queue-0.1.0.tgz",
      "integrity": "sha512-rVksvsnNCdJ/ohGc6xgPwyN8eheCxsiLM8mxuE/t/mOVqJewPuO1miLpTHQiRgTKCLexL4MeAFVagts7HmNZ2Q==",
      "dev": true
    }
  }
}
"""


def write_trees(root: Path) -> tuple[Path, Path]:
    api, web = root / "api", root / "web"
    api.mkdir(parents=True)
    web.mkdir(parents=True)
    (api / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (api / "uv.lock").write_text(UV_LOCK, encoding="utf-8")
    (web / "package.json").write_text(PACKAGE_JSON, encoding="utf-8")
    (web / "package-lock.json").write_text(PACKAGE_LOCK, encoding="utf-8")
    return api, web


class TreesTestCase(unittest.TestCase):
    """A scratch api and web tree, at 0.1.0 in all five entries."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.api, self.web = write_trees(self.root)


# --------------------------------------------------------------------------- #
# Version strings
# --------------------------------------------------------------------------- #


class TestParseVersion(unittest.TestCase):
    def test_accepts_an_x_y_z(self):
        self.assertEqual(rv.parse_version("0.1.0", "x"), (0, 1, 0))
        self.assertEqual(rv.parse_version("10.20.30", "x"), (10, 20, 30))

    def test_refuses_a_trailing_newline(self):
        # The regression worth naming: accepted once, written into a manifest as two
        # physical lines, and discovered behind a tag that had already been pushed.
        with self.assertRaises(rv.Refusal):
            rv.parse_version("0.2.0\n", "x")

    def test_refuses_near_misses(self):
        for bad in ("v0.2.0", "0.2", "0.2.0-rc1", "01.2.3", " 0.2.0", "0.2.0 ", ""):
            with self.subTest(bad=bad), self.assertRaises(rv.Refusal):
                rv.parse_version(bad, "x")

    def test_round_trips(self):
        self.assertEqual(rv.format_version(rv.parse_version("1.2.3", "x")), "1.2.3")


# --------------------------------------------------------------------------- #
# Commit classification
# --------------------------------------------------------------------------- #


class TestClassifyCommit(unittest.TestCase):
    def test_a_feature(self):
        self.assertEqual(rv.classify_commit("feat: gear list"), rv.FEATURE)
        self.assertEqual(rv.classify_commit("feat(dives): gear list"), rv.FEATURE)

    def test_everything_else_is_routine(self):
        for subject in (
            "fix: stop the chart flickering",
            "chore(deps): bump the postgres digest",
            "docs: say which ports Caddy needs free",
            "revert: the gear list",
            "ci: run the suite on every PR",
        ):
            with self.subTest(subject=subject):
                self.assertEqual(rv.classify_commit(subject), rv.ROUTINE)

    def test_the_bang_is_breaking_whatever_the_type(self):
        self.assertEqual(rv.classify_commit("feat!: new required variable"), rv.BREAKING)
        self.assertEqual(rv.classify_commit("fix(env)!: drop a default"), rv.BREAKING)

    def test_a_breaking_change_footer_is_breaking(self):
        for footer in ("BREAKING CHANGE:", "BREAKING-CHANGE:"):
            with self.subTest(footer=footer):
                message = f"fix: tidy the env\n\n{footer} SMTP_HOST is now required."
                self.assertEqual(rv.classify_commit(message), rv.BREAKING)

    def test_a_body_is_not_read_as_more_commits(self):
        message = "docs: install notes\n\n- feat!: this is a bullet, not a commit\n"
        self.assertEqual(rv.classify_commit(message), rv.ROUTINE)

    def test_unclassifiable_subjects(self):
        for subject in (
            '',
            'Revert "feat: gear list"',
            "feature: not one of the types",
            "feat:",
            "feat no colon",
            "Merge branch 'main'",
        ):
            with self.subTest(subject=subject):
                self.assertIsNone(rv.classify_commit(subject))

    def test_the_type_list_matches_the_one_ci_enforces(self):
        # `pr-title.yml` is what decides which subjects ever reach `main`. A type it
        # accepts and this file does not is a commit the script refuses to classify, on
        # a release day, in a repository where every title had already passed its check.
        workflow = (REPO_ROOT / ".github/workflows/pr-title.yml").read_text("utf-8")
        declared = [
            line.split(":", 1)[1].strip()
            for line in workflow.splitlines()
            if line.strip().startswith("TYPES:")
        ]
        self.assertEqual(len(declared), 1, "pr-title.yml should declare TYPES once")
        self.assertEqual(tuple(declared[0].split("|")), rv.COMMIT_TYPES)


class TestNextVersion(unittest.TestCase):
    def test_pre_1_0_breaking_is_a_minor(self):
        self.assertEqual(rv.next_version((0, 1, 0), rv.BREAKING), (0, 2, 0))

    def test_pre_1_0_feature_is_a_minor(self):
        self.assertEqual(rv.next_version((0, 1, 0), rv.FEATURE), (0, 2, 0))

    def test_pre_1_0_routine_is_a_patch(self):
        self.assertEqual(rv.next_version((0, 1, 0), rv.ROUTINE), (0, 1, 1))

    def test_from_1_0_breaking_is_a_major(self):
        self.assertEqual(rv.next_version((1, 4, 2), rv.BREAKING), (2, 0, 0))

    def test_from_1_0_feature_is_a_minor(self):
        self.assertEqual(rv.next_version((1, 4, 2), rv.FEATURE), (1, 5, 0))

    def test_from_1_0_routine_is_a_patch(self):
        self.assertEqual(rv.next_version((1, 4, 2), rv.ROUTINE), (1, 4, 3))


# --------------------------------------------------------------------------- #
# Locating a literal by where it sits, not by what the line says
# --------------------------------------------------------------------------- #


class TestJsonLocator(unittest.TestCase):
    def located(self, text, path):
        span = rv.locate_json_string(text, path, "fixture")
        return text[span.start : span.end], rv._line_of(text, span.start)

    def test_the_two_project_entries_and_not_the_dependency(self):
        root_value, _ = self.located(PACKAGE_LOCK, ("version",))
        own_value, own_line = self.located(PACKAGE_LOCK, ("packages", "", "version"))
        self.assertEqual((root_value, own_value), ("0.1.0", "0.1.0"))

        lines = PACKAGE_LOCK.split("\n")
        yocto = next(
            index + 1
            for index, line in enumerate(lines)
            if line == '      "version": "0.1.0",'
            and lines[index - 1].strip().startswith('"node_modules/yocto-queue"')
        )
        # The premise of the whole locator: the two lines are the same bytes, so the
        # only thing that can tell them apart is where they are.
        self.assertEqual(lines[own_line - 1], lines[yocto - 1])
        self.assertNotEqual(own_line, yocto)

    def test_agrees_with_the_json_parser(self):
        data = json.loads(PACKAGE_LOCK)
        self.assertEqual(self.located(PACKAGE_LOCK, ("version",))[0], data["version"])
        self.assertEqual(
            self.located(PACKAGE_LOCK, ("packages", "", "version"))[0],
            data["packages"][""]["version"],
        )

    def test_array_indices_are_part_of_a_path(self):
        text = '{"a": ["zero", {"b": "one"}]}'
        self.assertEqual(self.located(text, ("a", 0))[0], "zero")
        self.assertEqual(self.located(text, ("a", 1, "b"))[0], "one")

    def test_escapes_in_keys_and_values(self):
        text = '{"a\\"b": "va\\"lue"}'
        span = rv.locate_json_string(text, ('a"b',), "fixture")
        self.assertEqual(text[span.start : span.end], 'va\\"lue')

    def test_refuses_a_path_that_is_not_there(self):
        with self.assertRaises(rv.Refusal):
            rv.locate_json_string(PACKAGE_LOCK, ("nope",), "fixture")

    def test_refuses_a_path_that_is_not_a_string(self):
        with self.assertRaises(rv.Refusal):
            rv.locate_json_string(PACKAGE_LOCK, ("packages",), "fixture")
        with self.assertRaises(rv.Refusal):
            rv.locate_json_string(PACKAGE_LOCK, ("lockfileVersion",), "fixture")

    def test_refuses_a_path_that_resolves_twice(self):
        with self.assertRaises(rv.Refusal):
            rv.locate_json_string('{"v": "a", "v": "b"}', ("v",), "fixture")

    def test_refuses_trailing_content(self):
        with self.assertRaises(rv.Refusal):
            rv.locate_json_string('{"v": "a"} junk', ("v",), "fixture")

    def test_walks_past_empty_containers(self):
        text = '{"a": {}, "b": [], "c": "x", "d": 1, "e": null}'
        self.assertEqual(self.located(text, ("c",))[0], "x")

    def test_refuses_a_malformed_document(self):
        # The scanner is hand-written because `json.loads` throws the offsets away, so
        # every shape it can be handed badly is a refusal rather than a wrong offset.
        for text in (
            "",
            "{",
            '{"a": "b"',
            '{"a": "b}',
            '{"a" "b"}',
            "{a: 1}",
            '{"a": "b" "c": "d"}',
            '{"a": [',
            '{"a": "b",',
        ):
            with self.subTest(text=text), self.assertRaises(rv.Refusal):
                rv.locate_json_string(text, ("a",), "fixture")

    def test_refuses_a_malformed_array(self):
        for text in ('{"a": ["b"', '{"a": ["b" "c"]}'):
            with self.subTest(text=text), self.assertRaises(rv.Refusal):
                rv.locate_json_string(text, ("a", 0), "fixture")


class TestTomlLocator(unittest.TestCase):
    def test_the_project_table_and_not_a_key_that_ends_in_version(self):
        span = rv.locate_toml_table_key(PYPROJECT, "project", "version", "fixture")
        self.assertEqual(PYPROJECT[span.start : span.end], "0.1.0")
        self.assertEqual(rv._line_of(PYPROJECT, span.start), 3)

    def test_other_tables_keep_their_own_keys(self):
        span = rv.locate_toml_table_key(PYPROJECT, "tool.ruff", "target-version", "f")
        self.assertEqual(PYPROJECT[span.start : span.end], "py314")

    def test_refuses_a_table_that_is_not_there(self):
        with self.assertRaises(rv.Refusal):
            rv.locate_toml_table_key(PYPROJECT, "tool.poetry", "version", "fixture")

    def test_refuses_a_key_that_is_not_there(self):
        with self.assertRaises(rv.Refusal):
            rv.locate_toml_table_key(PYPROJECT, "project", "license", "fixture")

    def test_refuses_a_key_assigned_twice(self):
        doubled = '[project]\nversion = "0.1.0"\nversion = "0.2.0"\n'
        with self.assertRaises(rv.Refusal):
            rv.locate_toml_table_key(doubled, "project", "version", "fixture")

    def test_the_package_block_is_found_by_its_name(self):
        span = rv.locate_uv_lock_package_version(UV_LOCK, "opendiving-api", "fixture")
        self.assertEqual(UV_LOCK[span.start : span.end], "0.1.0")
        self.assertEqual(rv._line_of(UV_LOCK, span.start), 11)
        # `alembic` carries a byte-identical `version = "0.1.0"` line seven lines above.
        self.assertIn('name = "alembic"\nversion = "0.1.0"', UV_LOCK)

    def test_the_metadata_table_is_not_part_of_the_package_block(self):
        # `requires-dist` names `ruff` inside an inline table. Reading that as the
        # block's own `name` would make the block ambiguous and the lookup fail.
        span = rv.locate_uv_lock_package_version(UV_LOCK, "ruff", "fixture")
        self.assertEqual(UV_LOCK[span.start : span.end], "0.14.2")

    def test_refuses_a_package_that_is_not_there(self):
        with self.assertRaises(rv.Refusal):
            rv.locate_uv_lock_package_version(UV_LOCK, "nope", "fixture")

    def test_refuses_a_table_that_appears_twice(self):
        doubled = PYPROJECT + '\n[project]\nversion = "0.2.0"\n'
        with self.assertRaises(rv.Refusal):
            rv.locate_toml_table_key(doubled, "project", "version", "fixture")

    def test_refuses_a_package_named_twice(self):
        doubled = UV_LOCK + '\n[[package]]\nname = "opendiving-api"\nversion = "0.2.0"\n'
        with self.assertRaises(rv.Refusal):
            rv.locate_uv_lock_package_version(doubled, "opendiving-api", "fixture")


class TestPlanFile(TreesTestCase):
    def test_refuses_an_entry_that_does_not_read_the_expected_version(self):
        path = self.api / "pyproject.toml"
        group = [site for site in rv.sites(self.api, self.web) if site.path == path]
        with self.assertRaises(rv.Refusal) as caught:
            rv.plan_file(path, group, "9.9.9", "10.0.0")
        self.assertIn("not the expected", str(caught.exception))

    def test_refuses_a_locator_that_points_somewhere_else(self):
        # The line-set check is the guard that makes "anchored on position" testable,
        # so it gets a test of its own rather than being trusted because the splice is
        # correct today.
        path = self.web / "package-lock.json"
        text = path.read_text("utf-8")
        newline = text.index("\n")
        wrong = rv.Site(
            path,
            "a span that runs across a line break",
            lambda _text, _where: rv.Span(newline - 1, newline + 2, "wrong"),
        )
        with self.assertRaises(rv.Refusal):
            rv.plan_file(path, [wrong], text[newline - 1 : newline + 2], "0.2.0")


class TestChangedLineNumbers(unittest.TestCase):
    def test_reports_the_lines_that_moved(self):
        before = "a\nb\nc\n"
        self.assertEqual(rv.changed_line_numbers(before, "a\nB\nc\n", "f"), {2})
        self.assertEqual(rv.changed_line_numbers(before, before, "f"), set())

    def test_refuses_a_change_in_line_count(self):
        with self.assertRaises(rv.Refusal):
            rv.changed_line_numbers("a\nb\n", "a\nb\nc\n", "f")


# --------------------------------------------------------------------------- #
# Reading the current state
# --------------------------------------------------------------------------- #


class TestReaders(TreesTestCase):
    def test_every_entry_reads_the_same_version(self):
        self.assertEqual(
            set(rv.declared_versions(self.api, self.web).values()), {"0.1.0"}
        )

    def test_the_product_version(self):
        self.assertEqual(rv.current_product_version(self.api, self.web), (0, 1, 0))

    def test_refuses_when_the_lock_disagrees_with_the_manifest(self):
        # The loud one: `uv sync --locked` refuses this, and that build is api's
        # required `runtime-imports` check, so a bump that wrote only `pyproject.toml`
        # would open a pull request that can never merge.
        path = self.api / "uv.lock"
        path.write_text(
            UV_LOCK.replace(
                'name = "opendiving-api"\nversion = "0.1.0"',
                'name = "opendiving-api"\nversion = "0.2.0"',
            ),
            encoding="utf-8",
        )
        with self.assertRaises(rv.Refusal) as caught:
            rv.current_product_version(self.api, self.web)
        self.assertIn("uv.lock", str(caught.exception))

    def test_refuses_when_the_lockfile_disagrees_with_package_json(self):
        # The silent one: `npm ci` tolerates it, so nothing else would ever say so.
        (self.web / "package-lock.json").write_text(
            PACKAGE_LOCK.replace(
                '  "version": "0.1.0",', '  "version": "0.2.0",', 1
            ),
            encoding="utf-8",
        )
        with self.assertRaises(rv.Refusal):
            rv.current_product_version(self.api, self.web)

    def test_refuses_when_api_and_web_disagree(self):
        (self.api / "pyproject.toml").write_text(
            PYPROJECT.replace('version = "0.1.0"', 'version = "0.2.0"'), encoding="utf-8"
        )
        (self.api / "uv.lock").write_text(
            UV_LOCK.replace(
                'name = "opendiving-api"\nversion = "0.1.0"',
                'name = "opendiving-api"\nversion = "0.2.0"',
            ),
            encoding="utf-8",
        )
        with self.assertRaises(rv.Refusal) as caught:
            rv.current_product_version(self.api, self.web)
        self.assertIn("do not agree", str(caught.exception))

    def test_package_json_is_read_with_node(self):
        self.assertEqual(rv.read_package_json_version(self.web), "0.1.0")

    def test_refuses_a_manifest_with_no_version(self):
        (self.api / "pyproject.toml").write_text(
            '[project]\nname = "opendiving-api"\n', encoding="utf-8"
        )
        with self.assertRaises(rv.Refusal):
            rv.read_pyproject_version(self.api)

    def test_refuses_a_lock_that_names_the_project_zero_or_twice(self):
        for text in (
            UV_LOCK.replace('name = "opendiving-api"', 'name = "something-else"'),
            UV_LOCK + '\n[[package]]\nname = "opendiving-api"\nversion = "0.2.0"\n',
        ):
            (self.api / "uv.lock").write_text(text, encoding="utf-8")
            with self.subTest(text=text[:40]), self.assertRaises(rv.Refusal):
                rv.read_uv_lock_version(self.api)

    def test_refuses_a_lock_whose_version_is_not_a_string(self):
        (self.api / "uv.lock").write_text(
            UV_LOCK.replace(
                'name = "opendiving-api"\nversion = "0.1.0"',
                'name = "opendiving-api"\nversion = 1',
            ),
            encoding="utf-8",
        )
        with self.assertRaises(rv.Refusal):
            rv.read_uv_lock_version(self.api)

    def test_refuses_when_node_cannot_read_package_json(self):
        (self.web / "package.json").write_text("{ not json", encoding="utf-8")
        with self.assertRaises(rv.Refusal) as caught:
            rv.read_package_json_version(self.web)
        self.assertIn("node failed", str(caught.exception))

    def test_refuses_when_node_answers_undefined(self):
        (self.web / "package.json").write_text('{"name": "web"}\n', encoding="utf-8")
        with self.assertRaises(rv.Refusal) as caught:
            rv.read_package_json_version(self.web)
        self.assertIn("undefined", str(caught.exception))

    def test_refuses_a_package_json_version_that_is_not_a_string(self):
        (self.web / "package.json").write_text('{"version": 3}\n', encoding="utf-8")
        with self.assertRaises(rv.Refusal):
            rv.read_package_json_version(self.web)

    def test_refuses_a_lockfile_missing_a_project_entry(self):
        for text in (
            '{"packages": {"": {}}}',
            '{"version": "0.1.0", "packages": {"": {}}}',
            '{"version": 3, "packages": {"": {"version": "0.1.0"}}}',
        ):
            (self.web / "package-lock.json").write_text(text, encoding="utf-8")
            with self.subTest(text=text), self.assertRaises(rv.Refusal):
                rv.read_package_lock_versions(self.web)

    def test_a_directory_that_is_not_a_repository_is_a_refusal(self):
        with self.assertRaises(rv.Refusal) as caught:
            rv.version_tags(self.api)
        self.assertIn("failed", str(caught.exception))

    def test_node_sees_a_stray_newline_that_a_strip_would_hide(self):
        (self.web / "package.json").write_text(
            PACKAGE_JSON.replace('"version": "0.1.0"', '"version": "0.1.0\\n"'),
            encoding="utf-8",
        )
        self.assertEqual(rv.read_package_json_version(self.web), "0.1.0\n")
        with self.assertRaises(rv.Refusal):
            rv.current_product_version(self.api, self.web)


# --------------------------------------------------------------------------- #
# Rewriting
# --------------------------------------------------------------------------- #


class TestRewrite(TreesTestCase):
    def originals(self):
        return {
            self.api / "pyproject.toml": PYPROJECT,
            self.api / "uv.lock": UV_LOCK,
            self.web / "package.json": PACKAGE_JSON,
            self.web / "package-lock.json": PACKAGE_LOCK,
        }

    def test_writes_every_entry_and_nothing_else(self):
        written = rv.rewrite(self.api, self.web, "0.2.0")
        self.assertEqual(
            written,
            [
                (str(self.api / "pyproject.toml"), 3),
                (str(self.api / "uv.lock"), 11),
                (str(self.web / "package.json"), 3),
                (str(self.web / "package-lock.json"), 3),
                (str(self.web / "package-lock.json"), 9),
            ],
        )
        for path, original in self.originals().items():
            changed = rv.changed_line_numbers(
                original, path.read_text("utf-8"), str(path)
            )
            expected = {line for name, line in written if name == str(path)}
            self.assertEqual(changed, expected, path.name)

    def test_the_post_condition(self):
        # No entry of the structural kind still declares the old version.
        rv.rewrite(self.api, self.web, "0.2.0")
        self.assertEqual(
            set(rv.declared_versions(self.api, self.web).values()), {"0.2.0"}
        )

    def test_the_lookalike_lines_are_left_alone(self):
        rv.rewrite(self.api, self.web, "0.2.0")
        lock = (self.web / "package-lock.json").read_text("utf-8")
        parsed = json.loads(lock)
        self.assertEqual(parsed["packages"]["node_modules/yocto-queue"]["version"], "0.1.0")
        self.assertIn("yocto-queue-0.1.0.tgz", lock)

        pyproject = (self.api / "pyproject.toml").read_text("utf-8")
        self.assertIn('"ruff>=0.1.0"', pyproject)

        uv_lock = (self.api / "uv.lock").read_text("utf-8")
        self.assertIn('name = "alembic"\nversion = "0.1.0"', uv_lock)
        self.assertIn('specifier = ">=0.1.0"', uv_lock)

    def test_refuses_a_version_that_does_not_move_forward(self):
        for target in ("0.1.0", "0.0.9"):
            with self.subTest(target=target), self.assertRaises(rv.Refusal):
                rv.rewrite(self.api, self.web, target)

    def test_refuses_a_malformed_version_before_touching_anything(self):
        with self.assertRaises(rv.Refusal):
            rv.rewrite(self.api, self.web, "0.2.0\n")
        self.assertEqual(
            (self.api / "pyproject.toml").read_text("utf-8"), PYPROJECT
        )

    def test_the_entries_are_found_wherever_they_sit(self):
        # Nothing is anchored on a line number: shift the whole document and the
        # locators still find the same two entries in the lock.
        (self.web / "package-lock.json").write_text(
            PACKAGE_LOCK.replace('  "lockfileVersion": 3,\n', ""), encoding="utf-8"
        )
        rv.rewrite(self.api, self.web, "0.2.0")
        self.assertEqual(
            set(rv.declared_versions(self.api, self.web).values()), {"0.2.0"}
        )

    def test_nothing_is_written_when_a_later_file_refuses(self):
        # web's lock has grown a second `packages[""]` key, so its locator refuses -
        # after api's two files have already been located and spliced. A run that wrote
        # as it went would leave api bumped and web not, which `npm ci` tolerates and
        # api's lock check would report as a manifest mismatch rather than as this.
        (self.web / "package-lock.json").write_text(
            PACKAGE_LOCK.replace(
                '      "version": "0.1.0",\n      "dependencies"',
                '      "version": "0.1.0",\n      "version": "0.1.0",\n      "dependencies"',
            ),
            encoding="utf-8",
        )
        with self.assertRaises(rv.Refusal):
            rv.rewrite(self.api, self.web, "0.2.0")
        self.assertEqual((self.api / "pyproject.toml").read_text("utf-8"), PYPROJECT)
        self.assertEqual((self.api / "uv.lock").read_text("utf-8"), UV_LOCK)
        self.assertEqual((self.web / "package.json").read_text("utf-8"), PACKAGE_JSON)

    def test_refuses_when_an_entry_no_longer_reads_the_current_version(self):
        # Someone edited one by hand between the decision and the rewrite. The version
        # is now inconsistent, so there is no current product version to bump from.
        (self.api / "pyproject.toml").write_text(
            PYPROJECT.replace('version = "0.1.0"', 'version = "0.1.5"'), encoding="utf-8"
        )
        with self.assertRaises(rv.Refusal):
            rv.rewrite(self.api, self.web, "0.2.0")


# --------------------------------------------------------------------------- #
# The windows, and the decision
# --------------------------------------------------------------------------- #

GIT_ENV = {
    **os.environ,
    # A throwaway repository, isolated from every real configuration file: this must
    # never read or write the signing, hook or identity settings of a real checkout.
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}

GIT_IDENTITY = (
    "-c", "user.name=Test",
    "-c", "user.email=test@example.invalid",
    "-c", "commit.gpgsign=false",
    "-c", "init.defaultBranch=main",
)


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *GIT_IDENTITY, *args],
        check=True,
        env=GIT_ENV,
        capture_output=True,
        text=True,
    )


def make_repo(path: Path, subjects: list[str], tag_after_first: str | None) -> None:
    """A repository with one empty commit per subject, tagged after the first."""
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "--quiet")
    for index, subject in enumerate(subjects):
        git(path, "commit", "--allow-empty", "--no-verify", "-m", subject)
        if index == 0 and tag_after_first:
            git(path, "tag", tag_after_first)


class WindowsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.api, self.web = write_trees(self.root)

    def build(self, product, api, web, tag="v0.1.0"):
        product_repo = self.root / "product"
        make_repo(product_repo, ["chore: the first release", *product], tag)
        make_repo(self.api, ["chore: the first release", *api], tag)
        make_repo(self.web, ["chore: the first release", *web], tag)
        return {
            "opendiving": product_repo,
            "opendiving-api": self.api,
            "opendiving-web": self.web,
        }


class TestDecide(WindowsTestCase):
    def test_a_quiet_window_is_a_patch(self):
        repos = self.build(["docs: install notes"], ["fix: a 500"], ["fix: a wobble"])
        decision = rv.decide(repos, None)
        self.assertEqual(decision["version"], "0.1.1")
        self.assertEqual(decision["level"], rv.ROUTINE)
        self.assertEqual(decision["source"], "computed")

    def test_a_feature_anywhere_is_a_minor(self):
        repos = self.build([], ["fix: a 500"], ["feat: gear list"])
        self.assertEqual(rv.decide(repos, None)["version"], "0.2.0")

    def test_breaking_is_a_minor_below_1_0(self):
        repos = self.build(["feat!: a new required variable"], [], [])
        decision = rv.decide(repos, None)
        self.assertEqual(decision["version"], "0.2.0")
        self.assertEqual(decision["level"], rv.BREAKING)

    def test_an_empty_window_does_not_stop_the_release(self):
        # The lockstep escape, and the one place this deliberately does the opposite of
        # the implementation it is modelled on. Two of the three have nothing to say and
        # all three still take the product version.
        repos = self.build([], [], ["feat: gear list"])
        decision = rv.decide(repos, None)
        self.assertEqual(decision["version"], "0.2.0")
        self.assertEqual(decision["windows"]["opendiving"]["commits"], 0)
        self.assertEqual(decision["windows"]["opendiving-api"]["commits"], 0)

    def test_refuses_when_nothing_landed_anywhere(self):
        repos = self.build([], [], [])
        with self.assertRaises(rv.Refusal) as caught:
            rv.decide(repos, None)
        self.assertIn("Nothing has landed", str(caught.exception))

    def test_refuses_a_window_it_cannot_classify(self):
        repos = self.build([], [], ['Revert "feat: gear list"'])
        with self.assertRaises(rv.Refusal) as caught:
            rv.decide(repos, None)
        self.assertIn("Revert", str(caught.exception))

    def test_an_explicit_version_overrides_the_computation(self):
        repos = self.build([], [], ["fix: a wobble"])
        decision = rv.decide(repos, "1.0.0")
        self.assertEqual(decision["version"], "1.0.0")
        self.assertEqual(decision["source"], "explicit")
        self.assertIsNone(decision["level"])

    def test_an_explicit_version_survives_a_window_it_cannot_classify(self):
        repos = self.build([], [], ['Revert "feat: gear list"'])
        self.assertEqual(rv.decide(repos, "0.2.0")["version"], "0.2.0")

    def test_an_explicit_version_does_not_skip_the_consistency_checks(self):
        # Naming the number yourself settles what the commits mean. It does not settle
        # whether the five entries agree about where the release is starting from.
        repos = self.build([], [], ["fix: a wobble"])
        (self.api / "pyproject.toml").write_text(
            PYPROJECT.replace('version = "0.1.0"', 'version = "0.1.5"'), encoding="utf-8"
        )
        with self.assertRaises(rv.Refusal):
            rv.decide(repos, "0.2.0")

    def test_the_decision_names_the_tag_it_read_from(self):
        repos = self.build([], [], ["fix: a wobble"])
        self.assertEqual(rv.decide(repos, None)["base_tag"], "v0.1.0")

    def test_refuses_an_explicit_version_that_goes_backwards(self):
        repos = self.build([], [], ["fix: a wobble"])
        for target in ("0.1.0", "0.0.9"):
            with self.subTest(target=target), self.assertRaises(rv.Refusal):
                rv.decide(repos, target)

    def test_refuses_a_repository_with_no_release_tag(self):
        repos = self.build([], [], [], tag=None)
        with self.assertRaises(rv.Refusal) as caught:
            rv.decide(repos, None)
        self.assertIn("no vX.Y.Z tag", str(caught.exception))

    def test_refuses_a_tag_that_is_behind_the_manifests(self):
        # A bump merged and its tag push did not land. Bumping again from here skips a
        # version nothing ever published.
        repos = self.build([], [], ["fix: a wobble"])
        git(repos["opendiving-api"], "tag", "-d", "v0.1.0")
        git(repos["opendiving-api"], "tag", "v0.0.9", "HEAD")
        with self.assertRaises(rv.Refusal) as caught:
            rv.decide(repos, None)
        self.assertIn("newest tag is v0.0.9", str(caught.exception))

    def test_a_non_semver_v_tag_is_not_mistaken_for_a_release(self):
        repos = self.build([], [], ["fix: a wobble"])
        git(repos["opendiving-web"], "tag", "v0.2.0-rc1", "HEAD")
        self.assertEqual(rv.decide(repos, None)["version"], "0.1.1")

    def test_a_squash_body_does_not_inflate_the_count(self):
        repos = self.build([], [], ["fix: a wobble\n\n- feat: a bullet\n- feat: another"])
        decision = rv.decide(repos, None)
        self.assertEqual(decision["windows"]["opendiving-web"]["commits"], 1)
        self.assertEqual(decision["version"], "0.1.1")


# --------------------------------------------------------------------------- #
# The command line
# --------------------------------------------------------------------------- #


class TestMain(WindowsTestCase):
    def run_main(self, argv):
        import contextlib
        import io

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = rv.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_decide_prints_json_and_exits_zero(self):
        repos = self.build([], [], ["feat: gear list"])
        code, out, _ = self.run_main(
            [
                "decide",
                "--product", str(repos["opendiving"]),
                "--api", str(repos["opendiving-api"]),
                "--web", str(repos["opendiving-web"]),
            ]
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["version"], "0.2.0")

    def test_a_refusal_exits_three(self):
        repos = self.build([], [], [])
        code, out, err = self.run_main(
            [
                "decide",
                "--product", str(repos["opendiving"]),
                "--api", str(repos["opendiving-api"]),
                "--web", str(repos["opendiving-web"]),
            ]
        )
        self.assertEqual(code, rv.EXIT_REFUSED)
        self.assertEqual(out, "")
        self.assertIn("error:", err)

    def test_rewrite_exits_zero_and_reports_each_entry(self):
        code, _, err = self.run_main(
            ["rewrite", "--api", str(self.api), "--web", str(self.web), "--version", "0.2.0"]
        )
        self.assertEqual(code, 0)
        self.assertEqual(len(err.strip().splitlines()), 5)
        self.assertEqual(
            set(rv.declared_versions(self.api, self.web).values()), {"0.2.0"}
        )


if __name__ == "__main__":
    unittest.main()
