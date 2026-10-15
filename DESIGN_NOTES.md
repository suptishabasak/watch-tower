# Design notes: next iteration

## Shared fetching
Keep one `fetch_page()` boundary for the scheduler, manual checks, preview and future RSS refreshes. The short-lived cache is keyed by canonical URL plus watch/ignore selectors; it prevents duplicate concurrent work from repeatedly loading the same page. Domain throttling and bounded retries remain centralized there. Do not cache failures as successful snapshots, and preserve SSRF validation for the initial URL and every redirect/subresource.

## Noise learning
Treat normalization as a deterministic pipeline: remove known volatile tokens, collapse whitespace, filter common chrome, then compare snapshots. Add a per-monitor “learn as noise” action that records a selected diff line/signature in a `noise_rules` table. Apply exact normalized signatures first; only offer fuzzy rules with a visible preview and undo, to avoid silently suppressing real price/content changes. Keep original full-text snapshots so rules can be re-run and users can compare any two versions.

## Politeness
Use a per-host minimum interval shared across workers, a bounded concurrency pool, exponential backoff with jitter for transient failures, and respect `Retry-After` when supplied. Identify the crawler with a clear user-agent and contact URL. Never attempt to bypass CAPTCHA, login walls, robots restrictions, or rate limits; surface a “blocked” state and allow the user to pause or retry later. A production deployment should enforce outbound network restrictions as well as URL validation.

## Four design questions
1. **How do we avoid duplicate fetching?** Centralize all page loads, key the cache by URL and selectors, throttle per domain, and bound worker concurrency.
2. **How can users teach the monitor what is noise?** Let them mark a diff as noise, store normalized signatures per monitor, preview the impact, and undo rules.
3. **How do we behave politely?** Identify ourselves, throttle per host, honor retry hints, back off on transient errors, and stop on access challenges.
4. **How can users inspect versions?** Persist a complete text snapshot for every successful version, list versions by timestamp/hash, and compare any two selected snapshots with the existing diff renderer. Keep screenshot references alongside each version so a later overlay can use the same pair.

## Remaining implementation slices
- Full-text `VersionSnapshot` table linked to monitor, including timestamp, hash, text and screenshot filename; migrate old monitors with a synthetic “current baseline” version where possible.
- Compare view: two version selectors, server-side diff endpoint, reuse `DiffView`.
- Screenshot overlay: scale images to a common viewport, blend with adjustable opacity, and offer a blink toggle; show a clear warning when viewport sizes differ.
- Daily digest: scheduler job at configured local hour, query changes since last digest, send via configured channels, and persist the last successful digest cursor to avoid duplicates.
- Per-monitor RSS: RSS 2.0 feed containing recent changes with stable GUIDs and monitored-page links.
