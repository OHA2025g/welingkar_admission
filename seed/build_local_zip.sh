#!/usr/bin/env bash
# Builds frontend/public/downloads/weschool-portal.zip (no real .env files, no node_modules).
set -euo pipefail
cd /app
OUT=frontend/public/downloads
STAGE=$(mktemp -d)/weschool-portal
mkdir -p "$OUT" "$STAGE/seed"
set -a; . backend/.env; set +a
mongodump --uri "$MONGO_URL" --db "$DB_NAME" --gzip --archive="$STAGE/seed/weschool-seed.archive.gz" --quiet
echo "$DB_NAME" > "$STAGE/seed/SOURCE_DB.txt"
rsync -a --exclude node_modules --exclude build --exclude __pycache__ --exclude .git --exclude '.env' \
  --exclude .pytest_cache --exclude .ruff_cache --exclude 'public/downloads' --exclude local_storage \
  backend frontend memory README_LOCAL.md "$STAGE/"
cp scripts/build_local_zip.sh "$STAGE/seed/"
for VAR in JWT_SECRET OTP_PEPPER EMERGENT_EMAIL_KEY TWILIO_ACCOUNT_SID TWILIO_AUTH_TOKEN STRIPE_API_KEY STRIPE_WEBHOOK_SECRET \
           EMERGENT_LLM_KEY TIGRIS_ACCESS_KEY_ID TIGRIS_SECRET_ACCESS_KEY TWILIO_WHATSAPP_CONTENT_SID; do
  VAL="${!VAR:-}"
  [ "$VAL" = "sk_test_emergent" ] && continue
  if [ ${#VAL} -ge 8 ] && grep -rqF --exclude='*.gz' "$VAL" "$STAGE"; then
    echo "real value of $VAR found in bundle; aborting" >&2; exit 1
  fi
  if [ ${#VAL} -ge 8 ] && zcat "$STAGE/seed/weschool-seed.archive.gz" | grep -qaF "$VAL"; then
    echo "real value of $VAR found in DB snapshot; aborting" >&2; exit 1
  fi
done
rm -f "$OUT/weschool-portal.zip"
(cd "$(dirname "$STAGE")" && zip -qr9 "/app/$OUT/weschool-portal.zip" weschool-portal)
SIZE=$(stat -c %s "$OUT/weschool-portal.zip")
printf '{"file":"weschool-portal.zip","size_bytes":%s,"built_at":"%s"}\n' "$SIZE" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$OUT/weschool-portal.json"
rm -rf "$(dirname "$STAGE")"
echo "built $OUT/weschool-portal.zip ($SIZE bytes)"
