#!/usr/bin/env bash
# OpenDiving - install.
#
#   mkdir opendiving && cd opendiving
#   curl -LO https://github.com/opendiving/opendiving/releases/latest/download/install.sh
#   less install.sh          # it is about to write your .env - read it first
#   bash install.sh
#
# It checks this machine can run the stack, downloads `docker-compose.yml`, `Caddyfile` and
# `example.env`, and writes `.env` with the two secrets generated and the handful of values
# only you know filled in. Then it stops: the last thing it prints is the
# `docker compose up -d` for you to run.
#
# It deliberately does NOT start anything. Caddy asks Let's Encrypt for a certificate the
# moment it comes up, and a failed challenge - which is what a domain that does not point
# here yet gets you - counts against a rate limit that is per hostname and per hour. Whether
# DNS is ready is your call to make, not this script's.
#
# Everything below can be done by hand instead, in four commands and an editor:
# https://github.com/opendiving/opendiving/tree/main/docs/install.md. What a document cannot
# do is generate a secret, or check Docker and the ports and DNS before Caddy does.
#
# Options:
#   --version vX.Y.Z   install that release instead of the newest one
#   --help
#
# Unattended: any value that is already in the environment is used as-is and not asked for,
# so `DOMAIN=... SMTP_HOST=... EMAIL_FROM_ADDRESS=... bash install.sh` needs no terminal.

set -euo pipefail

REPO="https://github.com/opendiving/opendiving"
DOCS="$REPO/tree/main/docs"
VERSION="latest"

# ============================================================================
# Output
# ============================================================================

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    BOLD=$'\033[1m'; RED=$'\033[31m'; YELLOW=$'\033[33m'; GREEN=$'\033[32m'; DIM=$'\033[2m'; OFF=$'\033[0m'
else
    BOLD=""; RED=""; YELLOW=""; GREEN=""; DIM=""; OFF=""
fi

# Everything except the final note goes to stderr, so `bash install.sh > install.log` still
# shows you the questions and the warnings.
say()  { printf '%s\n' "$*" >&2; }
step() { printf '\n%s%s%s\n' "$BOLD" "$*" "$OFF" >&2; }
ok()   { printf '  %s✓%s %s\n' "$GREEN" "$OFF" "$*" >&2; }
warn() { printf '  %s!%s %s\n' "$YELLOW" "$OFF" "$*" >&2; WARNED=1; }
die()  { printf '\n%serror%s %s\n\n' "$RED" "$OFF" "$*" >&2; exit 1; }

WARNED=0
DNS_CONFIRMED=0

usage() {
    cat <<'USAGE'
Install OpenDiving into the current directory.

  bash install.sh [--version vX.Y.Z]

  --version vX.Y.Z   install that release rather than the newest one
  --help             this

It downloads docker-compose.yml, Caddyfile and example.env, writes .env, and stops
without starting anything.
USAGE
}

# ============================================================================
# Arguments
# ============================================================================

while [ $# -gt 0 ]; do
    case "$1" in
        --version) [ $# -ge 2 ] || die "--version needs a version, e.g. --version v0.4.0"; VERSION="$2"; shift 2 ;;
        --version=*) VERSION="${1#*=}"; shift ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; die "unknown option: $1" ;;
    esac
done

if [ "$VERSION" = "latest" ]; then
    ASSETS="$REPO/releases/latest/download"
else
    # Both spellings, because the tag is `v0.4.0` and the images are `0.4.0` and nobody
    # remembers which of the two this argument wants.
    case "$VERSION" in v*) TAG="$VERSION" ;; *) TAG="v$VERSION" ;; esac
    case "$TAG" in
        v[0-9]*.[0-9]*.[0-9]*) : ;;
        *) die "--version wants a released version like v0.4.0, not '$VERSION'." ;;
    esac
    ASSETS="$REPO/releases/download/$TAG"
fi

# ============================================================================
# Can this machine run it?
# ============================================================================

step "Checking this machine"

[ -w . ] || die "$PWD is not writable. Install somewhere you own - \`mkdir opendiving && cd opendiving\` is the usual shape."

command -v curl >/dev/null 2>&1 || die "curl is not installed, and it is how this script fetches the bundle. Install it, or follow $DOCS/install.md by hand."

if ! command -v docker >/dev/null 2>&1; then
    die "Docker is not installed.

  Install Docker Engine for your distribution - the official instructions are at
  https://docs.docker.com/engine/install/ - then run this again. This script will not
  install it for you: it is your machine's package manager and root that are involved,
  and that is a decision to make with your eyes open.

  Docker Desktop counts, and so does any current distribution package, as long as
  \`docker compose version\` works."
fi

if ! DOCKER_INFO="$(docker info 2>&1)"; then
    if printf '%s' "$DOCKER_INFO" | grep -qi 'permission denied'; then
        die "Docker is installed but this user cannot talk to it.

  Add yourself to the \`docker\` group and log in again:

      sudo usermod -aG docker \$USER

  Or run this script with sudo, remembering that the files it writes will be root's."
    fi
    die "Docker is installed but not running - \`docker info\` failed:

$(printf '%s' "$DOCKER_INFO" | tail -3)

  Start it (\`sudo systemctl start docker\`, or open Docker Desktop) and run this again."
fi

# `docker-compose` v1 is not this. The bundle uses `depends_on: condition:
# service_completed_successfully`, which only Compose v2 understands, and an operator with
# v1 on their PATH gets a parse error naming the key rather than the version.
if ! docker compose version >/dev/null 2>&1; then
    die "Docker is running, but the Compose plugin is missing.

  This bundle needs \`docker compose\` (the plugin), not \`docker-compose\` (the retired
  standalone v1): it depends on \`service_healthy\` and \`service_completed_successfully\`
  conditions that v1 cannot parse. Install \`docker-compose-plugin\` from the same Docker
  repository you got the engine from - https://docs.docker.com/compose/install/ - and run
  this again."
fi
ok "docker $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo '?'), $(docker compose version --short 2>/dev/null || echo 'compose v2')"

ENGINE_MAJOR="$(docker version --format '{{.Server.Version}}' 2>/dev/null | cut -d. -f1)"
case "$ENGINE_MAJOR" in
    ''|*[!0-9]*) : ;;
    *) [ "$ENGINE_MAJOR" -lt 25 ] && warn "Docker Engine $ENGINE_MAJOR is older than the 25 this bundle is documented against. It may well work; if the stack does not come up, upgrade before debugging anything else." ;;
esac

# Only the bundled Caddy publishes a port, and it wants both: 443 for the site and 80 for
# the ACME challenge that gets the certificate. Something already holding one of them is
# usually another reverse proxy, which is a supported setup and a different install.
port_taken() {
    if command -v ss >/dev/null 2>&1; then
        ss -ltn 2>/dev/null | grep -qE "[:.]$1[[:space:]]"
    elif command -v netstat >/dev/null 2>&1; then
        netstat -ltn 2>/dev/null | grep -qE "[:.]$1[[:space:]]"
    elif command -v lsof >/dev/null 2>&1; then
        lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
    else
        return 2
    fi
}

for PORT in 80 443; do
    if port_taken "$PORT"; then
        warn "Something is already listening on port $PORT. The bundled Caddy cannot start beside it - two proxies cannot both hold 80/443. If that is your own nginx, Traefik or NPM, this is a bring-your-own-proxy install: comment \`COMPOSE_PROFILES=proxy\` out of .env when this finishes and read $DOCS/reverse-proxy.md."
    fi
done

if [ -e .env ]; then
    die "There is already a .env here, and overwriting it is the one thing this script must not do.

  It holds POSTGRES_PASSWORD, which Postgres read once when its volume was created and
  never reads again: a freshly generated one would leave a database this .env cannot open,
  and the failure looks like an authentication bug rather than a config one. SECRET_KEY is
  the same shape of trouble - rotating it signs every session out.

  Edit the file you have (every setting is documented where it sits), or move it aside if
  this really is a fresh start. $DOCS/configuration.md is the reference."
fi

# ============================================================================
# The bundle
# ============================================================================

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Running from a checkout - or from a directory where the three files are already sitting
# next to this script - installs those rather than re-fetching a release. It is what makes
# a change to the bundle testable before it is tagged.
SCRIPT_DIR=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/docker-compose.yml" ] && [ -f "$SCRIPT_DIR/Caddyfile" ] && [ -f "$SCRIPT_DIR/example.env" ]; then
    step "Using the bundle next to this script"
    say "  $DIM$SCRIPT_DIR$OFF"
    cp "$SCRIPT_DIR/docker-compose.yml" "$SCRIPT_DIR/Caddyfile" "$TMP/"
    cp "$SCRIPT_DIR/example.env" "$TMP/env"
else
    step "Downloading the bundle"
    say "  $DIM$ASSETS$OFF"
    fetch() {
        if ! curl -fsSL -o "$2" "$ASSETS/$1"; then
            die "Could not download $1 from $ASSETS.

  If you asked for a specific version, check it exists at $REPO/releases. Otherwise this
  is a network or a GitHub problem, and the same three files can be fetched by hand -
  $DOCS/install.md has the commands."
        fi
    }
    fetch docker-compose.yml "$TMP/docker-compose.yml"
    fetch Caddyfile "$TMP/Caddyfile"
    # `example.env`, not `.env.example`: GitHub renames a release asset whose name starts
    # with a dot, so that URL would 404.
    fetch example.env "$TMP/env"
fi
ok "docker-compose.yml, Caddyfile, example.env"

# ============================================================================
# The values only you know
# ============================================================================

# Read from the terminal rather than from stdin: piping this script into bash makes stdin
# the script itself, and a `read` would eat it.
TTY=""
if [ -r /dev/tty ] && [ -w /dev/tty ]; then TTY=/dev/tty; fi

ask() {   # ask VAR "question" ["default"]
    local var="$1" question="$2" default="${3-}" answer=""

    # Already in the environment - an unattended install, or a second pass after a value
    # was rejected. Taken as given, empty included: an empty SMTP_USERNAME means something.
    if [ -n "${!var+set}" ]; then
        printf '  %s %s%s%s\n' "$question" "$DIM" "${!var:-(empty)}" "$OFF" >&2
        return 0
    fi

    [ -n "$TTY" ] || die "$var is not set and there is no terminal to ask on. Either run this script from a terminal, or set the values it needs in the environment: DOMAIN, SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD and EMAIL_FROM_ADDRESS."

    if [ -n "$default" ]; then
        printf '  %s %s[%s]%s ' "$question" "$DIM" "$default" "$OFF" > "$TTY"
    else
        printf '  %s ' "$question" > "$TTY"
    fi
    IFS= read -r answer < "$TTY" || answer=""
    [ -n "$answer" ] || answer="$default"
    printf -v "$var" '%s' "$answer"
}

ask_secret() {   # ask_secret VAR "question"
    local var="$1" question="$2" answer=""
    if [ -n "${!var+set}" ]; then
        printf '  %s %s%s%s\n' "$question" "$DIM" "$([ -n "${!var}" ] && echo '(set)' || echo '(empty)')" "$OFF" >&2
        return 0
    fi
    [ -n "$TTY" ] || die "$var is not set and there is no terminal to ask on."
    printf '  %s ' "$question" > "$TTY"
    stty -echo < "$TTY" 2>/dev/null || true
    IFS= read -r answer < "$TTY" || answer=""
    stty echo < "$TTY" 2>/dev/null || true
    printf '\n' > "$TTY"
    printf -v "$var" '%s' "$answer"
}

step "Your instance"
say "  ${DIM}Four answers. Everything else has a working default you can change later in .env.$OFF"

while :; do
    ask DOMAIN "Domain this instance is reached at, e.g. dives.example.com:"
    # A pasted address arrives with the scheme and sometimes a path attached, and DOMAIN is
    # a hostname: it becomes Caddy's site address, the passkey domain, and the host half of
    # every emailed sign-in link.
    TYPED="$DOMAIN"
    DOMAIN="$(printf '%s' "$DOMAIN" | tr '[:upper:]' '[:lower:]' | sed -e 's#^[a-z][a-z0-9+.-]*://##' -e 's#/.*$##' -e 's#[[:space:]]##g')"

    if printf '%s' "$DOMAIN" | grep -qE '^([0-9]{1,3}\.){3}[0-9]{1,3}$'; then
        die "$DOMAIN is an IP address, and Caddy cannot get a certificate for one.

  That install is real and documented - it serves plain HTTP and gives up passkeys with it -
  but it is not this script's happy path. Follow the 'LAN / no domain' block at the bottom of
  example.env, or $DOCS/reverse-proxy.md."
    fi
    if printf '%s' "$DOMAIN" | grep -qE '^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$'; then
        [ "$DOMAIN" = "$TYPED" ] || say "  ${DIM}using $DOMAIN$OFF"
        break
    fi
    if [ -n "$TTY" ]; then
        say "  ${YELLOW}!${OFF} That is not a hostname. Something like dives.example.com - no scheme, no path."
        unset DOMAIN
    else
        die "DOMAIN='$DOMAIN' is not a hostname. Something like dives.example.com - no scheme, no path."
    fi
done

# Sign-in is passwordless, so an instance that cannot send mail cannot be used - by anybody,
# including whoever installed it.
say ""
say "  ${DIM}Sign-in is an emailed link, so this needs an SMTP relay you already have -"
say "  ${DIM}your mail provider, your host's, or your own server. $DOCS/configuration.md$OFF"
while :; do
    ask SMTP_HOST "SMTP host, e.g. smtp.example.com:"
    SMTP_HOST="$(printf '%s' "$SMTP_HOST" | sed -e 's#^[a-z][a-z0-9+.-]*://##' -e 's#/.*$##' -e 's#[[:space:]]##g')"
    [ -n "$SMTP_HOST" ] && break
    [ -n "$TTY" ] || die "SMTP_HOST is required: ENVIRONMENT=production refuses to start without one."
    say "  ${YELLOW}!${OFF} Required - an instance that cannot send mail cannot be signed in to."
    unset SMTP_HOST
done

while :; do
    ask SMTP_PORT "SMTP port:" 587
    # shellcheck disable=SC2153  # assigned by ask(), through printf -v
    case "$SMTP_PORT" in
        ''|*[!0-9]*) : ;;
        *) [ "$SMTP_PORT" -ge 1 ] && [ "$SMTP_PORT" -le 65535 ] && break ;;
    esac
    [ -n "$TTY" ] || die "SMTP_PORT='$SMTP_PORT' is not a port number."
    say "  ${YELLOW}!${OFF} A port number. 587 for STARTTLS, 465 for implicit TLS."
    unset SMTP_PORT
done

ask SMTP_USERNAME "SMTP username (blank if the relay authenticates by IP):" ""
# The API only attempts a login when a username is set, so a password without one is a
# value that goes nowhere.
if [ -n "$SMTP_USERNAME" ]; then
    ask_secret SMTP_PASSWORD "SMTP password (not echoed):"
else
    SMTP_PASSWORD="${SMTP_PASSWORD-}"
fi

while :; do
    ask EMAIL_FROM_ADDRESS "Address the mail comes from:" "noreply@$DOMAIN"
    EMAIL_FROM_ADDRESS="$(printf '%s' "$EMAIL_FROM_ADDRESS" | sed 's#[[:space:]]##g')"
    if printf '%s' "$EMAIL_FROM_ADDRESS" | grep -qE '^[^@]+@[^@]+\.[^@]+$'; then
        break
    fi
    [ -n "$TTY" ] || die "EMAIL_FROM_ADDRESS='$EMAIL_FROM_ADDRESS' is not an email address."
    say "  ${YELLOW}!${OFF} An email address, on a domain your relay is allowed to send for."
    unset EMAIL_FROM_ADDRESS
done

# ============================================================================
# The values nobody should type
# ============================================================================

# Hex, not the `openssl rand -base64 24` the documentation suggests for a hand-written
# password: base64's `+/=` are fine in .env but `@ : / #` in a password have to be
# percent-encoded in the CRUD_ADMIN_DB_URL that docker-compose.yml derives, and a generated
# value that quietly rules that out is better than a footnote about it. 24 bytes is 192 bits
# either way.
gen_hex() {
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -hex "$1"
        return
    fi
    # -v matters: od collapses repeated identical lines into `*` without it, which would
    # silently shorten the result on the one-in-a-lot input that repeats.
    od -An -vN "$1" -tx1 /dev/urandom | tr -d ' \n'
}

SECRET_KEY="$(gen_hex 32)"
POSTGRES_PASSWORD="$(gen_hex 24)"
[ ${#SECRET_KEY} -eq 64 ] && [ ${#POSTGRES_PASSWORD} -eq 48 ] || die "Could not generate a secret: neither openssl nor /dev/urandom produced one. Install openssl and run this again - and do not fill SECRET_KEY in by hand with anything you thought of yourself."

# ============================================================================
# Write .env
# ============================================================================

ENV_FILE="$TMP/env"

# A value in .env is not read back the way it looks. Compose stops a bare value at the
# first ` #` and interpolates `$` in it, so an SMTP password of `pa$$w0rd # 1` arrives as
# `pa` - no error, no warning, and the first thing that notices is a sign-in email that
# never sends. Single quotes are literal and carry everything except a single quote, which
# is what the double-quoted branch is for. Verified against `docker compose config`.
env_quote() {
    local escaped
    case "$1" in
        "") printf '' ;;
        *[!A-Za-z0-9_@%+=:,./-]*)
            case "$1" in
                *\'*)
                    escaped="$1"
                    escaped="${escaped//\\/\\\\}"
                    escaped="${escaped//\"/\\\"}"
                    escaped="${escaped//$/\\$}"
                    printf '"%s"' "$escaped"
                    ;;
                *) printf "'%s'" "$1" ;;
            esac
            ;;
        *) printf '%s' "$1" ;;
    esac
}

# In place, one line at a time, because the comments around each setting are the
# documentation an operator has at 1am - the file is 300 lines of them and 20 of settings.
# The value goes through the environment rather than a `-v` assignment: awk interprets
# backslash escapes in `-v`, and an SMTP password containing one would arrive mangled.
set_env() {   # set_env KEY VALUE
    local written
    written="$(env_quote "$2")"
    if [ "$written" != "$2" ]; then
        say "  ${DIM}$1 written quoted - .env reads a bare value only as far as the first space or #$OFF"
    fi
    OD_KEY="$1" OD_VALUE="$written" awk '
        BEGIN { key = ENVIRON["OD_KEY"]; value = ENVIRON["OD_VALUE"]; done = 0 }
        !done && index($0, key "=") == 1 { print key "=" value; done = 1; next }
        { print }
        END { if (!done) exit 3 }
    ' "$ENV_FILE" > "$ENV_FILE.new" || die "example.env has no $1= line to set. This script and that template have drifted apart - install by hand instead: $DOCS/install.md"
    mv "$ENV_FILE.new" "$ENV_FILE"
}

# The same, for a setting that ships commented out.
enable_env() {   # enable_env KEY VALUE
    local written
    written="$(env_quote "$2")"
    OD_KEY="$1" OD_VALUE="$written" awk '
        BEGIN { key = ENVIRON["OD_KEY"]; value = ENVIRON["OD_VALUE"]; done = 0 }
        !done && index($0, "# " key "=") == 1 { print key "=" value; done = 1; next }
        { print }
        END { if (!done) exit 3 }
    ' "$ENV_FILE" > "$ENV_FILE.new" || die "example.env has no commented $1= line to enable. This script and that template have drifted apart - install by hand instead: $DOCS/install.md"
    mv "$ENV_FILE.new" "$ENV_FILE"
}

step "Writing .env"

set_env DOMAIN "$DOMAIN"
set_env SECRET_KEY "$SECRET_KEY"
set_env POSTGRES_PASSWORD "$POSTGRES_PASSWORD"
set_env SMTP_HOST "$SMTP_HOST"
set_env SMTP_PORT "$SMTP_PORT"
set_env SMTP_USERNAME "$SMTP_USERNAME"
set_env SMTP_PASSWORD "$SMTP_PASSWORD"
set_env EMAIL_FROM_ADDRESS "$EMAIL_FROM_ADDRESS"

# The template's default is `starttls`, which is right for 587 and silently wrong for 465:
# an implicit-TLS relay does not answer a plaintext greeting, and the first thing that finds
# out is somebody's sign-in link an hour after the install.
if [ "$SMTP_PORT" = "465" ]; then
    enable_env SMTP_TLS_MODE tls
    ok "SMTP_TLS_MODE=tls, because port 465 is implicit TLS"
fi

install -m 600 "$ENV_FILE" ./.env 2>/dev/null || { cp "$ENV_FILE" ./.env && chmod 600 ./.env; }
cp "$TMP/docker-compose.yml" ./docker-compose.yml
cp "$TMP/Caddyfile" ./Caddyfile

ok "SECRET_KEY and POSTGRES_PASSWORD generated"
ok ".env written, mode 600 - it holds both of them and your relay password"

# ============================================================================
# Does the domain point here?
# ============================================================================

# The single most common failed install: Caddy comes up, asks for a certificate for a name
# that resolves somewhere else or nowhere at all, and the site never answers. Worth knowing
# before `up -d` rather than from the logs afterwards.
resolve_a() {
    if command -v getent >/dev/null 2>&1 && getent ahostsv4 "$1" >/dev/null 2>&1; then
        getent ahostsv4 "$1" | awk '{print $1}' | sort -u
    elif command -v dig >/dev/null 2>&1; then
        dig +short A "$1" 2>/dev/null | grep -E '^([0-9]{1,3}\.){3}[0-9]{1,3}$' || true
    elif command -v host >/dev/null 2>&1; then
        host -t A "$1" 2>/dev/null | awk '/has address/ {print $NF}' || true
    fi
}

local_a() {
    if command -v ip >/dev/null 2>&1; then
        ip -o -4 addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1
    elif command -v ifconfig >/dev/null 2>&1; then
        ifconfig 2>/dev/null | awk '/inet /{print $2}' | sed 's/^addr://'
    fi
}

step "Checking DNS"
RESOLVED="$(resolve_a "$DOMAIN")"
LOCAL="$(local_a)"
if [ -z "$RESOLVED" ]; then
    warn "$DOMAIN does not resolve. Point its A/AAAA record at this machine and let it propagate before starting the stack - Caddy asks for a certificate as it comes up, and Let's Encrypt rate-limits failed challenges per hostname per hour."
else
    # Deliberately no call to an outside 'what is my IP' service: a self-hosting install
    # script should not report your address to a third party to tell you something it can
    # only get half right anyway. Behind NAT the two differ for a perfectly good reason,
    # which is why a mismatch is a warning and not a refusal.
    while IFS= read -r ADDR; do
        if [ -n "$ADDR" ] && printf '%s\n' "$LOCAL" | grep -qxF "$ADDR"; then
            DNS_CONFIRMED=1
        fi
    done <<EOF
$RESOLVED
EOF
    if [ "$DNS_CONFIRMED" = "1" ]; then
        ok "$DOMAIN resolves to this machine"
    else
        warn "$DOMAIN resolves to $(printf '%s' "$RESOLVED" | tr '\n' ' ')- which is not an address on this machine. Expected if this machine is behind NAT or a cloud load balancer forwarding 80/443 here; wrong if you meant a different machine."
    fi
fi

# ============================================================================
# What now
# ============================================================================

printf '\n%sReady.%s %s\n\n' "$BOLD" "$OFF" "$PWD"
printf '    docker compose up -d\n\n'
printf '  Then open %shttps://%s%s and ask for a sign-in link - the first account to sign\n' "$BOLD" "$DOMAIN" "$OFF"
printf '  in is yours. Certificates, images and migrations all happen on that first start;\n'
printf '  docker compose logs -f is where it reports in.\n\n'

if [ "$DNS_CONFIRMED" != "1" ]; then
    printf '  %s!%s Point %s at this machine %sbefore%s that command.\n\n' "$YELLOW" "$OFF" "$DOMAIN" "$BOLD" "$OFF"
fi
if [ "$WARNED" = "1" ]; then
    printf '  %sThere were warnings above.%s\n\n' "$DIM" "$OFF"
fi
printf '  %sEvery setting is documented in .env where it sits. %s/configuration.md%s\n\n' "$DIM" "$DOCS" "$OFF"
