# API access

An API key lets a script or a tool of your own use your account through the API: a nightly backup,
a spreadsheet that pulls your dives, a converter that pushes them in. The web app and the OpenDiving
iOS app need none of this — they sign in the ordinary way. A key belongs to one account on one
instance, so everything below works the same on an instance you run and on
<https://opendiving.app>; `dives.example.com` stands for whichever one yours is.

## Creating a key

Sign in, open **Settings → Authentication**, and press **Create API key** on the **API keys** card.
The form asks three things:

- **Name** — a label for your own benefit, up to 50 characters: `laptop`, `backup cron`.
- **Access** — **Read only**, the default, or **Read and write**. Pick read only unless the tool has
  to change something.
- **Expires after** — **30 days**, **90 days**, **1 year** (the default) or **Never**. An expired
  key stops working and stays on the card, marked **Expired**, until you revoke it.

**Create key** shows the secret once, in a field labelled **New API key** with a **Copy** button.
Copy it before you press **Done**: only a fingerprint of it is kept, so it cannot be shown again —
lose it and the fix is a new key. Every key begins `odk_`; the card names each one by its first
twelve characters, its access, and when it was created, last used and expires.

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
`/export/archive` is a zip with the uploaded files as well.

A failed key — unknown, expired, revoked, or on an account that has asked to be deleted — gets the
same `401` `"User not authenticated."` as any other bad credential.

## What a key cannot do

- **A read-only key cannot write.** It may use `GET`, `HEAD` and `OPTIONS`; any other method answers
  `403` `"This API key is read-only."` before anything happens.
- **No key can manage sign-in.** The routes for API keys, passkeys, signed-in devices, the check-in
  link and the invite link, the request to change the sign-in email address, and deleting the
  account all answer a key with `403` `"This needs a signed-in browser or app, not an API key."` A
  stolen key cannot lock you out or mint itself a successor.
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
that instance's release has them. The interactive reference that renders it, `/docs`, is open
only on a `local` instance and behind an operator account on `staging`; a `production` instance
does not serve it. The web app renders the same document at `/developers` on every instance, with no
sign-in — on the project's instance that is <https://opendiving.app/developers>.

## Proposing a species photo

A species' photograph is a file from Wikimedia Commons, chosen by a rule until whoever runs the
instance hides it or pins another. Any account can propose a better file, and a write key can do it
from a tool. A proposal changes nothing until the operator accepts it, which makes it the species'
photo, or declines it.

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
write key; a key for the Anthropic API; and an address or page where Wikimedia can reach you.

```bash
git clone https://github.com/opendiving/opendiving-api && cd opendiving-api
export OPENDIVING_API_KEY=odk_...      # a Read and write key
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

Nothing needs switching on: every account can create keys. Two settings bound them —
`API_KEY_MAX_PER_USER` and `API_KEY_CREATE_RATE_LIMIT_PER_USER` under
[Sign-in](configuration.md#sign-in).

Proposals wait on **Admin → Species**, under the *Proposed* chip, each beside the photo it would
replace; accepting and declining happen there, in a signed-in session, since no key is an operator.
The daily limit on proposing is `SPECIES_PHOTO_PROPOSAL_RATE_LIMIT_PER_USER`, 100, over
`SPECIES_PHOTO_PROPOSAL_RATE_LIMIT_WINDOW_SECONDS`, a day; like the API's other limits it is
described in `opendiving-api`'s
[`src/.env.example`](https://github.com/opendiving/opendiving-api/blob/main/src/.env.example)
rather than in [configuration.md](configuration.md).
