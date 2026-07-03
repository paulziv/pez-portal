#!/usr/bin/env bash
# apply_account_report_loader_and_refresh_fix.sh
#
# Fixes a second instance of the same bug we found and fixed in
# truage_activation's loading shell, plus its own version of the dead
# /refresh call cleaned up in run_daily().
#
# 1) Same missing-id bug: <div class="loader-sub"> (no id) but the JS does
#    getElementById('loader-sub') and gets null. Setting .textContent on
#    that null throws — synchronously, at the top level of the page's
#    startup script, before the code that loads the Auth0 SDK and calls
#    loadReport(). Net effect: the Account Manager report's manual "run
#    new report" button spins forever with zero network activity, exactly
#    like truage_activation's did. Same fix: add the id, guard both
#    elements in cycle(), and wrap the bootstrap call in try/catch so a
#    future similar typo can't repeat this failure mode.
#
# 2) The POST /refresh handler (used by the manual refresh button) forwarded
#    a request to {_UPSTREAM}/refresh — but truage-pulse has no /refresh
#    endpoint, so this always 404'd. Its result wasn't even used by the
#    frontend. Replaced with a true no-op, since /audit/report always
#    computes fresh data on every call regardless.
#
# USAGE:
#   Run this from the root of your pez-portal checkout:
#     bash apply_account_report_loader_and_refresh_fix.sh
#
# Does not commit or push — review `git diff` and commit on your own schedule.

set -euo pipefail

TARGET="app/routers/truage_account/routes.py"

if [[ ! -f "$TARGET" ]]; then
  echo "ERROR: $TARGET not found."
  echo "Run this script from the root of your pez-portal checkout."
  exit 1
fi

if grep -q 'id="loader-sub"' "$TARGET"; then
  echo "NOTE: This fix already appears to be applied to $TARGET. No changes made."
  exit 0
fi

if ! grep -q '<div class="loader-sub">' "$TARGET"; then
  echo "NOTE: $TARGET doesn't look like the expected pre-fix state"
  echo "(has changed since this script was written). Skipping to avoid a bad"
  echo "patch application. Check manually if unsure."
  exit 0
fi

PATCH_FILE="$(mktemp)"
trap 'rm -f "$PATCH_FILE"' EXIT

cat > "$PATCH_FILE" << 'PATCH_EOF'
diff --git a/app/routers/truage_account/routes.py b/app/routers/truage_account/routes.py
index 5243955..73e1c83 100644
--- a/app/routers/truage_account/routes.py
+++ b/app/routers/truage_account/routes.py
@@ -106,7 +106,7 @@ _SHELL = """<!DOCTYPE html>
   <div class="loader-card">
     <div class="loader-ring"></div>
     <div class="loader-msg" id="loader-msg">Connecting to HubSpot&hellip;</div>
-    <div class="loader-sub">Hang tight &mdash; this usually takes 30&ndash;45 seconds</div>
+    <div class="loader-sub" id="loader-sub">Hang tight &mdash; this usually takes 30&ndash;45 seconds</div>
     <div class="steps">
       <div class="step pending" id="step-1"><span class="step-icon">&#x25CB;</span><span>Authenticating with HubSpot API</span></div>
       <div class="step pending" id="step-2"><span class="step-icon">&#x25CB;</span><span>Fetching account manager records</span></div>
@@ -141,7 +141,13 @@ _SHELL = """<!DOCTYPE html>
     const msgEl = document.getElementById('loader-msg');
     const subEl = document.getElementById('loader-sub');
     function cycle() {{
-      if (!msgEl) return;
+      // Same fix as truage_activation's shell: guard BOTH elements, not
+      // just msgEl. A missing id="loader-sub" here let an uncaught
+      // TypeError abort the whole synchronous startup script before it
+      // ever reached the code that loads the Auth0 SDK and calls
+      // loadReport() — the visible symptom was the manual refresh button
+      // spinning forever with zero network activity.
+      if (!msgEl || !subEl) return;
       const [h, s] = LOAD_MSGS[i % LOAD_MSGS.length];
       msgEl.textContent = h; subEl.textContent = s; i++;
       _msgTimer = setTimeout(cycle, 3500);
@@ -299,7 +305,11 @@ _SHELL = """<!DOCTYPE html>
     }} catch(e) {{ btn.textContent = '↻ Refresh'; btn.disabled = false; }}
   }}
 
-  startLoadingMessages(0); _startSteps();
+  try {{
+    startLoadingMessages(0); _startSteps();
+  }} catch (e) {{
+    console.error('Cosmetic loading-UI init failed (non-fatal):', e);
+  }}
   const sdk = document.createElement('script');
   sdk.src = 'https://cdn.auth0.com/js/auth0-spa-js/2.0/auth0-spa-js.production.js';
   sdk.onload = () => {{ const rem = _cooldownSecs(); if (rem > 0) showCooldown(rem); else loadReport(); }};
@@ -483,12 +493,12 @@ async def proxy_report(user: UserClaims = Depends(_require)) -> HTMLResponse:
 
 @router.post("/refresh")
 async def refresh_report(user: UserClaims = Depends(_require)) -> JSONResponse:
-    try:
-        async with httpx.AsyncClient(timeout=10) as client:
-            resp = await client.post(f"{_UPSTREAM}/refresh")
-        return JSONResponse({"status": "triggered", "upstream": resp.status_code})
-    except Exception as exc:
-        return JSONResponse({"status": "error", "detail": str(exc)}, status_code=502)
+    # truage-pulse has no /refresh endpoint — /audit/report computes fresh
+    # on every call, so there's nothing to separately trigger. This used
+    # to forward a POST to that nonexistent upstream endpoint (always
+    # 404, silently ignored by the frontend either way). Now a true no-op;
+    # the frontend's subsequent loadReport() call gets fresh data regardless.
+    return JSONResponse({"status": "triggered"})
 
 
 @router.get("/api/status")
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
echo "After deploying: the Account Manager report's 'run new report' button"
echo "should work normally, and there will be no more 404 in the logs for"
echo "POST nacstam.up.railway.app/refresh."
