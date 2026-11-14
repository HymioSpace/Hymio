# Task experience and proactive work

Status: Implemented

## Overview

One personal assistant coordinates durable outcomes. Short replies, memory writes and small device
operations stay in the conversation. Background work has an independent bounded execution, a
business timeline and explicit waiting/resumption conditions. Home shows changes requiring attention;
the task board owns the full inventory and date agenda.

## Ownership and execution

Hymio owns task intent, triggers, waiting conditions, progress and results. Oath owns execution,
leases, tool state and delegated contexts. A task binds its subagent; UI activity is derived from
owner-scoped durable execution records, independent of model-authored progress notes. Coding apps
use the same activity contract. Detailed traces remain one drill-down away.

A task wait records reason, next action, optional resume time and actor. Human decisions do not
cause automatic work retries. Time-based continuation uses the task itself, with an idempotent
wake identity, generation checks and bounded intervention. Failed external effects are never
implicitly replayed. Pausing/cancelling invalidates future continuation.

## Context-originated opportunities

Nostalgia extensions may propose evidence-grounded opportunities during dreaming. Suggestions are
published only after context commit and delivered durably with stable identities. Hymio deduplicates
against prior suggestions and existing work. Discovery may prepare a low-risk research task; actions
requiring a decision remain suggestions until accepted. No observation alone grants external-action
authority. The source, evidence and decision remain visible in task history and administration.

## Presentation and administration

Task detail leads with current state, next action and output. A compact timeline separates milestone
updates from raw execution. iOS uses native material on floating navigation/composer surfaces,
with reduced-transparency fallback. Dates group schedules without assigning invented deadlines.
Nostalgia administration exposes the effective proposal prompt, runtime state, opportunities and
owner-scoped original/derived data through authenticated server-side adapters. Credentials are never
returned to the browser. Browsing is bounded; mutations require explicit actions and stable IDs.

## Current continuation scope

Tasks created as independent work are started by Backend in bounded children, default two per
user. Existing conversational work can be captured without dispatching it twice. Waiting records
use user/time/external/device/retry reasons. Non-human waits require an explicit follow-up time;
event-specific device/connector wakeups remain future adapters. Each run permits five automatic
checks. A user continuation is persisted before submission and resumes the bound context with a
stable message identity. Schedules and reminders keep their existing occurrence deadlines.

Home shows unseen attention changes and bounded previews, alongside context opportunities; the
task board retains all work. iOS offers a chronological schedule view. Semantic timeline entries
are separate from the latest 60 execution activity entries and detailed traces.
