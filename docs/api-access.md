# API access

An API key lets a script or a tool of your own use your account through the API: a nightly backup, a
spreadsheet that pulls your dives, a converter that pushes them in. The web app and the OpenDiving
iOS app need none of this — they sign in the ordinary way — and an AI assistant or another app that
speaks MCP can [connect without one](#connecting-an-app-through-mcp). A key belongs to one account
on one instance, so everything below works the same on an instance you run and on
<https://opendiving.app>; `dives.example.com` stands for whichever one yours is.

## Creating a key

Sign in, open **Settings → Authentication**, and press **Create API key** on the **API keys** card.
The form asks three things:

- **Name** — a label for your own benefit, up to 50 characters: `laptop`, `backup cron`.
- **Expires after** — **30 days**, **90 days**, **1 year** (the default) or **Never**. An expired
  key stops working and stays on the card, marked **Expired**, until you revoke it.
- **Key permissions** — what the key may do, ticked per part of the logbook as **Read**,
  **Create & edit** and **Delete**, with **Select all** to tick everything. Only reading dives is
  ticked to begin with, and a key needs at least one. Tick what the tool needs and nothing more —
  [What a key may do](#what-a-key-may-do) says what each one covers.

**Create key** shows the secret once, in a field labelled **New API key** with a **Copy** button.
Copy it before you press **Done**: only a fingerprint of it is kept, so it cannot be shown again —
lose it and the fix is a new key. Every key begins `odk_`; the card names each one by its first
twelve characters and when it was created, last used and expires, and lists what it may do.

Creating a key sends a notice to the account's email address, and no setting turns that off. A key
you did not make is the event it exists for.

## Using it

Send the key on the `Authorization` header, as a bearer token. Everything is under `/api/v1`:

```bash
KEY=odk_...
curl -H "Authorization: Bearer $KEY" https://dives.example.com/api/v1/dives
```

The natural read for a backup is the export, the same files the export button in the app downloads:

```bash
curl -H "Authorization: Bearer $KEY" -o logbook.divejson \
  https://dives.example.com/api/v1/export/divejson
```

`/export/divejson` is the whole logbook as one DiveJSON document; `/export/uddf` is UDDF for
Subsurface and the tools that read it; `/export/csv` is one row per dive for a spreadsheet; and
`/export/archive` is a zip with the uploaded files as well. With permissions chosen, the first
request needs `dives:read`, and every export `export:read` and `files:read` together.

A failed key — unknown, expired, revoked, or on an account that has asked to be deleted — gets the
same `401` `"User not authenticated."` as any other bad credential.

## What a key may do

A key does what its permissions allow and nothing else. Each one names a part of the logbook and an
action — `dives:read`, `gear:write`, `trips:delete` — so reading, creating and editing, and deleting
are granted separately, for dives, drafts, sites, trips, gear, people, contacts, courses,
certifications, tags, check-in details and presets alike. `profile` and `preferences` have a read and
a write each; `files:read` and `files:write` cover downloading and uploading files, `export:read` the
exports and `import:write` importing a logbook. `species:write` is a write with no read beside it,
as `import:write` is: it covers resolving a species — adding one a search found to the catalog every
account shares — and proposing and withdrawing a species photo, while reading species takes
`dives:read`. A key with `dives:write` and not `species:write` still logs dives, attaching species already
in the catalog. `GET /api/v1/user/api-key-permissions` lists the full set.

Some operations need more than one: an export, as above, or downloading a certification card, which
takes `certifications:read` and `files:read`. The schema names what each operation needs — see [The
contract](#the-contract). A request the key's permissions do not cover answers `403` `"Permission
not granted for this operation."` before the route runs, and so does every route no permission
names. `GET /api/v1/user` returns only the fields `profile:read` and `preferences:read` grant, and a
`PATCH` to it needs the write permission for every field it sends: one field outside them refuses
the whole update with `403`.

Keys made before permissions existed carry one of two older kinds of access instead, shown on the
card as **Read only** and **Read and write**; the web app and the iOS app make only keys with
chosen permissions. Read only may use `GET`, `HEAD` and `OPTIONS`, and any other method answers
`403` `"This API key is read-only."`; read and write may do what a signed-in browser can, short of
the list below. Neither can be narrowed: to restrict one, create a key with the permissions it needs
and revoke the old one.

## What a key cannot do

- **No key can manage sign-in.** The routes for API keys, MCP connections, passkeys, signed-in
  devices, the check-in link and the invite link, short-lived download links, the request to change the
  sign-in email address, and deleting the account all answer a key with `403` `"This needs a
  signed-in browser or app, not an API key."` — whatever its permissions. A stolen key cannot lock
  you out or mint itself a successor.
- **No key is an operator.** On an account that runs the instance, a key still acts as an ordinary
  diver: the operator's admin routes refuse it, and `GET /api/v1/user` reports `is_superuser` false.

Rate limits are the account's, not the key's. A script that pulls the export every few minutes uses
up the same allowance the export button draws on.

## Keep it out of the browser

A key is for server-side and command-line tools. The API answers browsers from one origin only — the
instance's own web app — so a page on any other site cannot call it, and a key written into browser
JavaScript is a key published to everyone who loads that page. Keep it where you keep other
passwords: an environment variable, a file only you can read, a secret store.

## Revoking a key

Press the bin icon on its row and confirm **Revoke**. The key is refused from its very next request,
whatever holds it, and the account gets a second notice saying so. To rotate a key, create the new
one, move the tool over, and revoke the old one.

A key is not a signed-in device. **Signing other devices out leaves keys working**, and so does an
operator rotating `SECRET_KEY`, because keys are not signed with it — each one ends only when it is
revoked or expires.

## The contract

Every instance serves its OpenAPI document at `/api/v1/openapi.json`, with no key and whatever its
`ENVIRONMENT` — on the project's instance that is <https://opendiving.app/api/v1/openapi.json>. It
is generated from the routes themselves, so it lists every path, parameter and response shape as
that instance's release has them, and each operation a permission covers carries what it needs under
`x-opendiving-permissions`, as `{"anyOf": [[...], ...]}`: a list of alternatives, each of which
needs every permission in it. The interactive reference that renders it, `/docs`, is open only on a
`local` instance and behind an operator account on `staging`; a `production` instance does not serve
it. The web app renders the same document at `/developers` on every instance, with no sign-in — on
the project's instance that is <https://opendiving.app/developers>.

## Connecting an app through MCP

An AI assistant, or any other app that speaks the Model Context Protocol, can work with your logbook
without a key, on an instance whose operator has switched it on. **Settings → MCP** shows the server
address, `https://dives.example.com/api/v1/mcp`; where Settings has no MCP section, the instance
does not offer it. Add the address in the app's MCP or connector settings, and the app sends you to
OpenDiving to sign in and choose what it may do. The page names the app — with **Unverified name**
when the app chose that name itself — and where it returns you, and lists the permissions the app
asked for — `dives:read` alone when it asked for none — with every read among them but check-in's
ticked to begin with. You can grant fewer, never more. **Allow selected permissions** connects it;
**Deny** sends it back with nothing.

A connection can do what you allowed and nothing more: the app is offered only the operations those
permissions cover. The app can upload files of up to 10 MiB each, and a download — an export, a dive
file — of up to 50 MiB comes back as a link the app fetches with its own token. What no key can do,
no connection can either: nothing on the list above, and it is never the operator. Approving a
connection needs you signed in, so neither a key nor another connection can make one. Unlike
creating a key, connecting sends no email.

**Connected applications**, on the same page, lists each one with its permissions and when it
connected and was last used. **Revoke** ends it from the app's next request; connecting again takes
your approval again. The app holds a fifteen-minute token that it renews, and an app that goes thirty
days without renewing it has to ask again. A renewal presented twice is taken as a copied token and
revokes the connection.

## Importing dives

A key with `import:write` and `files:write` can bring dives in with one request, applied at once and
with no review — the way the iOS app imports what it downloads from a dive computer:

```bash
curl -X POST -H "Authorization: Bearer $KEY" -H "Idempotency-Key: $(uuidgen)" \
  -F file=@dive-1.fit -F file=@dive-2.fit \
  'https://dives.example.com/api/v1/imports?apply=true'
```

Each file is a `file` part, in any format the logbook import reads, and a zip of them is one too.
The answer is `201` and the applied import: a `dives` row for each dive the files hold, saying
whether it is new, modified, unchanged or skipped and why. It never waits — it goes ahead whether or
not the account has an import waiting for a review, and holds no file on the server — and it is in
the import history like any other. Without `apply=true` the upload is held for a review instead,
one per account at a time, which the web app or the iOS app finishes.

**Keep one `Idempotency-Key` for one set of files, and send it again when you retry.** A repeat under
the key writes nothing and answers the import the first request made; it is a `409` while the first
is still running, and a `410` once that import has been deleted or has expired. A request that was
refused leaves the key unused. A `429` is the account's import budget and says nothing about the
files; `413` is too much at once or past the account's storage limit; and when no file can be read
at all, the answer is the first file's: `415` for bytes nothing here reads, `422` for a malformed
file. A file that cannot be read beside others that can stops nothing, and its row in `members` says
why.

Where a second computer's recording joins a dive, the one that comes first in the account's order of
dive computers is shown by default. `GET /api/v1/dive-computers` lists them, first to last, and
`PUT /api/v1/dive-computers/order` with `{"serials": ["D9772626", "253810000400"]}` sets that order;
the first needs `dives:read`, the second `dives:write`. Changing it changes no dive already stored.

## Proposing a species photo

A species' photograph is a file from Wikimedia Commons, chosen by a rule until whoever runs the
instance hides it or pins another. Any account can propose a better file, and a key with
`species:write` can do it from a tool. A proposal changes nothing until the operator accepts it, which
makes it the species' photo, or declines it.

```bash
curl -X POST -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"file": "Pterois miles 1.jpg", "note": "The whole animal, in open water."}' \
  https://dives.example.com/api/v1/species/<uuid>/photo-proposals
```

`file` is a Commons file title, with or without `File:`, or its file-page URL. `note` is optional,
up to 500 characters, and is what the operator reads beside the photo, with your name. The species'
`uuid` is on your life list, `GET /api/v1/user/species`, and its read, `GET /api/v1/species/<uuid>`,
says in `accepts_photo_proposals` whether it takes proposals: it is false once the operator has
chosen the photo by hand.

- **`201`** and the proposal, `waiting`. One waits per account and species: proposing again
  replaces it with a new proposal under a new `uuid`, and the old one is gone.
- **`409`** when the species does not accept proposals, when the file is its photo already, or when
  the operator declined that file for that species before — a decline holds whoever proposes it
  next.
- **`422`** for a title that is not a raster image file; **`404`** for an unknown species; **`429`**
  past the account's daily limit of proposals, 100 unless the operator changed it.

Proposing asks Wikimedia nothing: the title is checked for its shape only. The instance asks Commons
about the file when the operator's *Species* screen shows it, or when the operator accepts it.

`GET /api/v1/species-photo-proposals` lists your own proposals, newest first, paged with `page` and
`items_per_page`, and `?status=` narrows it to `waiting`, `accepted`, `declined`, `withdrawn` or
`closed`. Each carries its species, file, note and status, the reason when a decline gave one, and
when it was made and decided. `closed` means the operator chose the photo another way — pinned a
different file or hid it — without ruling on yours. `DELETE /api/v1/species-photo-proposal/<uuid>`
withdraws one that is waiting; one already settled answers `409`.

### Rating the photos with a model

`opendiving-api` carries a script that does the proposing for you. For each species on your life
list, it gathers the photographs Wikidata and Commons hold for it, shows them to a model beside the
one the instance stores, and proposes the one the model judges clearly better, with the model's
reason as the note. It runs on your own machine from a checkout of that repository, and is not in
the image. It needs [uv](https://docs.astral.sh/uv/), which fetches the Python the project pins; a
key with `dives:read` and `species:write`; a key for the Anthropic API; and an address or page where
Wikimedia can reach you.

```bash
git clone https://github.com/opendiving/opendiving-api && cd opendiving-api
export OPENDIVING_API_KEY=odk_...      # dives:read and species:write
export ANTHROPIC_API_KEY=sk-ant-...
uv run --extra dev python scripts/propose_species_photos.py \
  --instance https://dives.example.com --contact you@example.com --dry-run --limit 5
```

`--extra dev` is what installs the model's SDK; a bare `uv run` does not. `--dry-run` proposes
nothing and prints what it would have proposed, and `--limit` caps how many species go to the model;
drop both for a real run, and `--help` lists the rest. A species you have already proposed for —
waiting, accepted or declined — is never rated again, nor one whose photo the operator chose or that
has no Wikidata item, so a run can stop anywhere and the next one carries on. Reaching the daily
limit stops it cleanly. It ends with one summary line — species read, skipped and why, rated,
proposed, refused, answered none, and the tokens spent — printed too when the instance or the model
stops it partway. It exits `0` on a finished run or at the daily limit, `1` when the instance or
the model failed, and `2` when `OPENDIVING_API_KEY` is not set.

**What it sends where.** Wikidata and Commons are asked from your machine, one request at a time,
under a `User-Agent` carrying `--contact`, which
[Wikimedia's policy](https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy)
requires of every client; the contact goes nowhere else. The model provider is sent the names of the
species on your life list and, for each, the public Commons thumbnails as 250 px images with their
titles and sizes — the bytes, never a link to fetch. Nothing of your dives goes to either.

**What it costs** is the model's tokens, billed to the Anthropic key. One run on the project's
instance, on 2026-11-14, rated 37 species with the default model, `claude-opus-5-5`, at the default
effort, low, for 133,896 input and 3,623 output tokens: about 3,600 and 100 per species. At that
model's $4 and $20 per million, that run cost about $0.61, or $1.60 per hundred species. It is one
run's figure; a fuller pool costs more. The output tokens include the model's thinking, so
`--effort` — `low`, `medium` or `high` — is the control that moves them most, and `--model` names
another model.

## For the operator

Nothing needs switching on for keys: every account can create them. Two settings bound them —
`API_KEY_MAX_PER_USER` and `API_KEY_CREATE_RATE_LIMIT_PER_USER` under
[Sign-in](configuration.md#sign-in). MCP is off as it ships; `MCP_ENABLED` under
[Optional features](configuration.md#optional-features) turns it on.

Proposals wait on **Admin → Species**, under the *Proposed* chip, each beside the photo it would
replace; accepting and declining happen there, in a signed-in session, since no key is an operator.
The daily limit on proposing is `SPECIES_PHOTO_PROPOSAL_RATE_LIMIT_PER_USER`, 100, over
`SPECIES_PHOTO_PROPOSAL_RATE_LIMIT_WINDOW_SECONDS`, a day; like the API's other limits it is
described in `opendiving-api`'s
[`src/.env.example`](https://github.com/opendiving/opendiving-api/blob/main/src/.env.example)
rather than in [configuration.md](configuration.md).
