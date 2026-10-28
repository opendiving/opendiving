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

## For the operator

Nothing needs switching on: every account can create keys. Two settings bound them —
`API_KEY_MAX_PER_USER` and `API_KEY_CREATE_RATE_LIMIT_PER_USER` under
[Sign-in](configuration.md#sign-in).
