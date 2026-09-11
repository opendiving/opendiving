<!--
Prompts, not a checklist — replace each line with your answer and delete the ones that don't
apply. There is nothing here to tick.
-->

What changed, and why.

Touched the bundle? Say what you verified it with — `docker compose config`, the scratch install, a
real machine. CONTRIBUTING.md, "Verifying a change to the bundle", has all three.

Does an existing install have to do anything by hand — copy the new compose file, add a variable,
run a command? That is a breaking change in the sense CONTRIBUTING.md defines, whatever it does to
the code, and the release notes need to say so.

Changed a setting, a default or a step? The `docs/` page that documents it moves in this PR, not the
next one. `example.env` is documentation too — the paragraph above a setting is what an operator has
at 1am.

Did something non-obvious bite you? That is a `DECISIONS.md` section, and it belongs in this PR.
