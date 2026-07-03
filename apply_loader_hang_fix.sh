#!/usr/bin/env bash
# apply_loader_hang_fix.sh
#
# Fixes the "run new report" card spinning forever with no error.
#
# Root cause, confirmed via browser console + a real JS-engine repro (not
# a guess): the loading shell's HTML has
#     <div class="loader-msg" id="loader-msg">...</div>
#     <div class="loader-sub">...</div>                <- no id!
# but the JS does:
#     const subEl = document.getElementById('loader-sub');   // -> null
#     ...
#     subEl.textContent = s;   // Uncaught TypeError
#
# That call happens SYNCHRONOUSLY at the top level of the page's startup
# script (`startLoadingMessages(0);`), before the code that creates the
# Auth0 SDK <script> tag and wires up `sdk.onload = () => loadReport()`.
# An uncaught exception at that point halts the rest of the script block
# entirely — so the SDK is never loaded, loadReport() is never called, and
# the user is left staring at the static initial "Connecting to
# HubSpot…" markup forever, with zero network activity and zero visible
# error (unless they open DevTools).
#
# This fix:
#   1. Adds the missing id="loader-sub" so getElementById finds it.
#   2. Hardens cycle() to guard subEl the same way msgEl was already
#      guarded, so a similar future typo degrades gracefully instead of
#      throwing.
#   3. Wraps the startLoadingMessages(0)/_startSteps() bootstrap call in
#      try/catch, so an exception in this purely cosmetic code can never
#      again block the Auth0 SDK load and loadReport() that follow it.
#
# Verified with a Node.js repro simulating the exact DOM interaction:
# confirmed the uncaught exception blocks downstream code with the old
# markup+JS, and confirmed downstream code runs in both the fixed-markup
# case and the defensive-fallback case.
#
# USAGE:
#   Run this from the root of your pez-portal checkout:
#     bash apply_loader_hang_fix.sh
#
# Does not commit or push — review `git diff` and commit on your own schedule.

set -euo pipefail

TARGET="app/routers/truage_activation/routes.py"

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
diff --git a/app/routers/truage_activation/routes.py b/app/routers/truage_activation/routes.py
index 3f9f253..2dab969 100644
--- a/app/routers/truage_activation/routes.py
+++ b/app/routers/truage_activation/routes.py
@@ -237,7 +237,7 @@ _SHELL = """<!DOCTYPE html>
   <div class="loader-card">
     <div class="loader-ring"></div>
     <div class="loader-msg" id="loader-msg">Connecting to HubSpot&hellip;</div>
-    <div class="loader-sub">Hang tight &mdash; this usually takes 30&ndash;45 seconds</div>
+    <div class="loader-sub" id="loader-sub">Hang tight &mdash; this usually takes 30&ndash;45 seconds</div>
     <div class="steps">
       <div class="step pending" id="step-1">
         <span class="step-icon">&#x25CB;</span>
@@ -291,7 +291,15 @@ _SHELL = """<!DOCTYPE html>
     const msgEl = document.getElementById('loader-msg');
     const subEl = document.getElementById('loader-sub');
     function cycle() {{
-      if (!msgEl) return;
+      // Guard BOTH elements, not just msgEl. This exact asymmetry — one
+      // missing id="loader-sub" on the markup — previously let an uncaught
+      // TypeError here abort the whole synchronous startup script before
+      // it ever reached the code that loads the Auth0 SDK and calls
+      // loadReport(). The visible symptom was the loading spinner running
+      // forever with no network activity at all: nothing downstream of
+      // this line ever got a chance to execute. A missing element should
+      // degrade this cosmetic message rotation, not silently break page load.
+      if (!msgEl || !subEl) return;
       const [h, s] = LOAD_MSGS[i % LOAD_MSGS.length];
       msgEl.textContent = h;
       subEl.textContent = s;
@@ -496,9 +504,18 @@ _SHELL = """<!DOCTYPE html>
     }}
   }}
 
-  // Start message rotation and step progression immediately
-  startLoadingMessages(0);
-  _startSteps();
+  // Start message rotation and step progression immediately. Wrapped in
+  // try/catch deliberately: these are purely cosmetic (the rotating status
+  // text and step checklist), and an uncaught exception here must never be
+  // able to block the code below that actually loads the Auth0 SDK and the
+  // report — that's exactly what happened when a missing id="loader-sub"
+  // let an exception here silently kill page load entirely.
+  try {{
+    startLoadingMessages(0);
+    _startSteps();
+  }} catch (e) {{
+    console.error('Cosmetic loading-UI init failed (non-fatal):', e);
+  }}
 
   // Bootstrap Auth0 SDK — then check cooldown before firing loadReport
   const sdk = document.createElement('script');
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
echo "After deploying: the 'run new report' card should load normally."
echo "You can confirm in DevTools Console — the old 'Cannot set properties"
echo "of null' error should no longer appear on page load."
