# Reverse-engineered WodApp API

WodApp (`ws.paynplan.nl`) has no official public API. All integration is based on network traffic captured from the WodApp mobile app (HAR analysis). There was no alternative: WodApp is the sole source of gym schedule and user data, and no SDK or webhook system exists.

**Consequence:** The API contract is implicit and unversioned. WodApp can change endpoints, field names, or authentication behaviour at any time without notice, breaking WodPlanner silently. The hardcoded version string (`14.0`) and the `nl_NL` locale hint are fragile integration points. Any WodApp app update is a potential breaking change.
