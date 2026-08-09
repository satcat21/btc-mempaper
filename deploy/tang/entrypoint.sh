#!/bin/sh
# Start a Tang server, generating signing and exchange keys on first run.
set -eu

DB=${TANG_DB:-/var/lib/tang}
PORT=${TANG_PORT:-7500}
LIBEXEC=/usr/libexec

mkdir -p "$DB"

if [ -z "$(ls -A "$DB" 2>/dev/null)" ]; then
    echo "Generating Tang signing and exchange keys in $DB"
    "$LIBEXEC/tangd-keygen" "$DB"
fi

# tangd-keygen writes two keys: one for signing the advertisement and one for
# key exchange. clevis pins the signing key, so print only that one - printing
# both and leaving the choice to the reader is a coin flip, since the files are
# named after their thumbprints and sort arbitrarily.
echo "Pin this thumbprint in mempaper as tang_thumbprint:"
for jwk in "$DB"/*.jwk; do
    [ -e "$jwk" ] || continue
    if jose jwk use -i "$jwk" -r -u verify -o /dev/null 2>/dev/null; then
        printf '  %s\n' "$(jose jwk thp -i "$jwk")"
    fi
done

echo "Serving tangd on 0.0.0.0:$PORT (db=$DB)"
exec socat TCP-LISTEN:"$PORT",reuseaddr,fork,bind=0.0.0.0 EXEC:"$LIBEXEC/tangd $DB"
