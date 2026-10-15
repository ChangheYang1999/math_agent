# Exact Pro model discovery

**Verdict: BLOCKED — PRO_UNAVAILABLE. Zero Pro inference requests.**

On 2026-10-15 UTC, discovery used a new disposable tab **1707788771** in the
existing authenticated Chrome instance/profile. The unrelated original tab was
neither opened nor read. The bridge was connected and initially had zero active
requests, pending requests, and pending commands.

| Observed model | Bridge ID | UI availability | Selected |
| --- | --- | --- | --- |
| GPT-6 | `model-gpt-6` | Enabled radio | Yes |
| GPT-5.6 Sol | `model-gpt-5-6-sol` | Enabled radio | No |
| GPT-6 Pro / Astra | None observed | No exact enabled choice exposed | No |

The normal **Select model** control was also opened. It exposed the same two
model radios. Extra High was selected: bridge effort `xhigh`, visible status
“Extra High, 4 of 5.”, slider index 3 on the range 0–4. A separate control said
“Locked, opens access options”; its wording does not identify an exact Pro model.
No locked control was bypassed or selected, no account setting was changed, and
no message was submitted in the discovery tab.

Evidence: [UI controls](pro_picker_ui.json), [cropped picker screenshot](pro_picker.png),
[actual bridge models/efforts](pro_bridge_discovery.json), and
[initial bridge health](bridge_initial_health.json).

The observed blocker is **(c), no exact Pro choice selectable in this chat/profile**.
It is not evidence of a subscription entitlement and does not establish that Pro
is unavailable in every account or surface. There is no observed enabled Pro
control for a selector fix to recover. The adapter correctly refuses to treat
GPT-6 with `xhigh` as Pro, and no speculative Astra alias was introduced.

Production configuration remains leaf **GPT-6 Pro**, internal **GPT-6 Extra High**.
The actual coordinator radio label is GPT-6; the disposable live demonstration
uses that explicit label while retaining exact `xhigh`. All non-Pro demonstration
leaves are marked `TEST_ONLY_EXTRA_HIGH_LEAF_OVERRIDE`. Neither that demonstration
nor deterministic review tests constitute a genuine Pro pass.

The bounded Pro report and same-session Pro follow-up are **NOT_RUN**. They can
resume when an exact enabled Pro identity is selectable and verifiable through
the ordinary picker in this profile. No model inference was needed for discovery.
