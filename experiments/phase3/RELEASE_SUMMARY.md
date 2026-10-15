# Math Research Tree — Phase 3 review

The focused changes preserve the durable Leaf Report → Parent Response → next
prompt protocol, exact browser model verification, and all eight previously
live-verified bridge patches. One additional recovery fix is verified offline
and included as source only. Production roles remain GPT-6 Pro leaves and GPT-6 Extra High internal
coordinators. Prior project data and experiment evidence remain outside this
source-only release.

## Focused implementation

- [Human review](src/math_research_agent/scheduler.py) and the
  [dashboard](src/math_research_agent/static/dashboard.html) keep exact artifact
  versions pending through questions, deferral and refresh. Revisions create
  fresh approval gates; approving a stale version is refused. Prompt and report
  approvals remain distinct.
- [Tree behavior](src/math_research_agent/store.py) and
  [configuration](src/math_research_agent/config.py) preserve recursive model
  transitions, weighted maximum leaf capacity, safe pause/resume boundaries and
  event-driven optional communication after mandatory Parent feedback.
- [Bridge setup](bridge/README.md) reproduces pinned upstream
  `0ffdae90239988f253058c05253226152acd55d2` using the
  [reviewed manifest](bridge/manifest.json): eight unchanged historical patches
  plus [resume_roles.patch](bridge/patches/resume_roles.patch). The new three-line
  fix reuses the existing current-DOM role helper during recovery. It does not
  weaken exact key/text checks or add Send actions. The failed earlier composer
  candidate remains excluded.
- [Packaging](scripts/package_source.py) accepts an optional standalone release
  summary, preserving the earlier fix summary in the workspace.

## Validation status

- **OFFLINE_PASS:** 35 focused Python regression tests; 23 focused upstream
  checks; the [recovery fixture](bridge/tests/resume_roles.mjs) reproduces failure
  before the fix and correct matching afterward, preserving legacy and
  missing-boundary behavior. Simulated approvals do not represent a human decision.
- **LIVE_PASS — local UI only:** the actual dashboard displayed the modal,
  retained two questions, created a revised version and restored the pending
  hash/discussion after refresh and an idle restart. Research transport for this
  exercise was explicitly simulated.
- **BLOCKED:** no enabled exact GPT-6 Pro identity was exposed in the observed
  picker. Zero Pro inference calls; no substitute is labeled Pro.
- **WAITING_FOR_HUMAN:** the offline demonstration's prompt version 2 remains
  pending in the dashboard on port 8766. Codex has not clicked an approval button.
  Review the original English version before choosing approval; this does not
  authorize a real Pro request.
- **LIVE_FAIL / HALTED:** the real-browser project, explicitly labeled
  `TEST_ONLY_EXTRA_HIGH_LEAF_OVERRIDE`, made four requests. Bootstrap and both
  Leaf reports completed. The first Parent assessment failed after confirmed
  full submission of 16,701 characters with `CANONICAL_RECOVERY_UNCERTAIN`.
  Completed pairs: **0/6**. Two Parent obligations remain durable; no second
  round or uncertain request was resent. A later visible Parent reply remains
  an uncommitted diagnostic candidate.
- **NOT_RUN:** deployment and live retest of the new recovery patch. The active
  checkout and installed browser extension retain the eight prior patches. The
  nine-patch source recipe passed fresh pinned application, exact checks and an
  idempotent rerun. That offline result does not repair the historical failed
  terminal or establish a live continuation pass.

The final recorded bridge state has zero active/pending requests or commands.
The original Chrome instance and unrelated conversation were preserved. The
separate review dashboard remains idle behind the pending human gate.

Run instructions and production settings are in [README.md](README.md). The
focused regressions are [review tests](tests/test_review_dashboard.py),
[tree tests](tests/test_tree_dynamics.py) and
[bridge tests](tests/test_bridge_transport.py). Detailed live records, databases,
credentials, caches and the third-party runtime are excluded from this package.
