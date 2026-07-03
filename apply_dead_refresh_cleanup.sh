#!/usr/bin/env bash
# apply_dead_refresh_cleanup.sh
#
# Removes a harmless-but-confusing leftover: truage_account/routes.py's
# run_daily() called POST {_UPSTREAM}/refresh against truage-pulse before
# fetching the report — but truage-pulse has never had a /refresh
# endpoint. That call always 404'd, and its result was silently discarded
# either way (wrapped in bare try/except: pass), so it did nothing except
# add a confusing 404 to the logs every single day.
#
# It was almost certainly copy-pasted from truage_activation's run_daily(),
# which genuinely needs a POST /refresh to kick off a background pipeline
# before polling for results. truage-pulse's architecture is different —
# GET /audit/report computes and returns the full report synchronously in
# one blocking call (hence the 120s timeout in the retry loop below it) —
# so there was never anything for a /refresh call to trigger.
#
# No behavior change: the call's result was never checked. This is a pure
# cleanup, removing dead code and log noise.
#
# USAGE:
#   Run this from the root of your pez-portal checkout:
#     bash apply_dead_refresh_cleanup.sh
#
# Does not commit or push — review `git diff` and commit on your own schedule.

set -euo pipefail

TARGET="app/routers/truage_account/routes.py"

if [[ ! -f "$TARGET" ]]; then
  echo "ERROR: $TARGET not found."
  echo "Run this script from the root of your pez-portal checkout."
  exit 1
fi

if ! grep -q 'await client.post(f"{_UPSTREAM}/refresh")' "$TARGET"; then
  echo "NOTE: The dead /refresh call doesn't appear to be present in $TARGET"
  echo "(already removed, or the file has changed since this script was written)."
  echo "No changes made."
  exit 0
fi

PATCH_FILE="$(mktemp)"
trap 'rm -f "$PATCH_FILE"' EXIT

cat > "$PATCH_FILE" << 'PATCH_EOF'
diff --git a/app/routers/truage_account/routes.py b/app/routers/truage_account/routes.py
index 19fedc9..5243955 100644
--- a/app/routers/truage_account/routes.py
+++ b/app/routers/truage_account/routes.py
@@ -517,14 +517,18 @@ async def status(user: UserClaims = Depends(_require)) -> dict:
 
 
 async def run_daily() -> str:
-    """Fetch /audit/report directly (blocking endpoint), cache when a full report arrives."""
+    """Fetch /audit/report directly (blocking endpoint), cache when a full report arrives.
+
+    Unlike truage_activation's upstream, truage-pulse has no /refresh
+    endpoint — /audit/report computes and returns the full report
+    synchronously in one call (hence the 120s timeout below), so there's
+    nothing to separately trigger. A leftover `POST {_UPSTREAM}/refresh`
+    call used to sit here too, copied from truage_activation's pattern; it
+    always 404'd (harmlessly, since its result was discarded either way)
+    and only added confusing noise to the logs. Removed.
+    """
     import asyncio
     log.info("truage_account.run_daily: starting")
-    try:
-        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
-            await client.post(f"{_UPSTREAM}/refresh")
-    except Exception:
-        pass
     # /audit/report is a blocking endpoint — retry up to 5× with a 2-min timeout each.
     for attempt in range(5):
         try:
PATCH_EOF

echo "Applying patch to $TARGET..."
git apply --whitespace=nowarn "$PATCH_FILE"
echo "Patch applied."

echo "Verifying $TARGET compiles..."
python3 -m py_compile "$TARGET"
echo "Compiles OK."

echo ""
echo "Done. Review with: git diff $TARGET"
echo "This script did not commit or push — that's on you."
echo ""
echo "Expected effect: the daily 'POST nacstam.up.railway.app/refresh ... 404'"
echo "log line will no longer appear. Everything else about the Account"
echo "Manager report's daily send is unchanged."
