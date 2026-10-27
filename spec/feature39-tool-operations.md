# Tool operations and HTTP collection health

Status: Implementing

## Overview

The operator console separates tool execution from client turn latency. A dedicated Tools page
compares terminal outcomes, execution latency and traffic across tools. HTTP monitoring reports
collection health independently of query success: an accessible Prometheus with a failed Backend
target is a collection failure, not an empty traffic window.

Tool aggregates use existing Oath counters and histograms through a bounded Backend Prometheus
bridge. Time windows are explicit. Counter increases are sampling estimates, not exact audit
counts; sparse traffic, first samples, service restarts and retention can limit coverage. A zero
observation denominator has no success rate or latency. Histograms describe execution, exclude
approval/queue waiting, and may omit terminals that never entered execution. Unknown outcomes and
cancellations stay in the terminal denominator. No prompt, arguments, result bodies or user IDs
are used as metric labels. Trace investigation remains the source for individual invocation facts.

Queries are fixed and administrator-only. Refresh requests never overlap, stop in hidden tabs and
use a small set of aggregates; this page does not load the overview's client/compaction/host panels.
Per-query failures remain visible. Healthy collection without a recently observed tool terminal
shows an explicit empty state; failed or absent collection targets have separate guidance.

Cloud preparation emits an Oath observability environment file pointing to the generated private
network scrape target. Operators keep it in their persistent Oath startup environment. The admin
HTTP panel exposes failed/missing targets so a lost deployment setting is visible immediately.
