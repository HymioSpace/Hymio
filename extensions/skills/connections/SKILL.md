---
name: connections
description: Read connected services such as Gmail, calendar and task lists.
---

# Connections

Run `oath-cli help connections` for available operations. The connections CLI exposes the
user's configured sources and bounded reads. Inspect connection status before requesting data;
a configured source and a granted account connection are different states. Use returned cursors
for further results. Authorization takes place in the product UI, not through model-supplied
credentials. Retain source references when summarizing findings.
