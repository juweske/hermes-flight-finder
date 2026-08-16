# Milestone 4: Watch Checking And Deterministic Deals

## Purpose

Turn saved watches into a local price tracker. `watch check --json` must query each watch, record
normalized price observations, and return only genuine threshold or relative-drop alerts.

## Design

Persist `PriceObservation` and `AlertRecord` alongside watches in the existing versioned JSON
state document. A pure `DealEvaluator` compares the current best price to prior observations and
configured thresholds. A `WatchCheckService` coordinates flexible search, history persistence,
evaluation, and duplicate-alert suppression.

On a first observation, only a configured target price can alert. A relative drop uses the best
prior observation. An alert with the same watch, price, and date pair is suppressed; an improved
price or a new date pair can alert. Provider failures propagate as errors and are never turned
into no-result responses.

## Verification

Test target-price alerts, baseline behavior, percentage drops, duplicate suppression, history
persistence, provider failures, and `watch check --json`. Run all normal quality gates.

## Status

Complete. `watch check` records the current best date-price observation, evaluates target-price
and relative-drop rules, persists alert records, and suppresses repeated alerts for the same
price/date pair. The full offline suite and static quality gates pass.
