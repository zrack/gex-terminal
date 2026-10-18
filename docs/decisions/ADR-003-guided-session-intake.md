# ADR-003 — Bounded Local Session Intake

Date: 2026-10-18. Status: accepted for GEX-INTAKE-STUDY-001.

## Decision

Accept a user-selected complete captured-session file as bounded bytes over the
existing capability-protected loopback API. Reuse the capture hash verifier in
memory, then retain only allowlisted market messages and effective assumptions
in a bounded per-server registry. Display safe source/time/model context before
the user chooses a capture-sequence cutoff. Replay that prefix through the
production consumer and return the existing strict, opaque checkpoint string.
Saved receipts embed it and reproduce without the original file or registry.

Capture headers and normalized-message extensions may contain private content.
Verify original bytes first, then discard arbitrary metadata and extensions;
never reflect raw verifier exceptions or private labels in browser responses.
Alias source contract identifiers consistently to preserve linkage without
copying private contract labels. Generate provenance from the full verified
content digest and chosen sequence.
No raw upload is written to the receipt workspace. Cancel/discard and server
shutdown release retained session state; the registry also bounds retention.

The existing checkpoint format stays strict and versioned. Integrity verification
does not confer source authenticity, licensing, live certification or predictive
validity. Offline loading of an authorized historical capture is distinct from
acquiring or qualifying a live provider stream.

## Alternatives And Consequences

Accepting browser-supplied filesystem paths gives the browser unnecessary local
read authority. A second importer duplicates normalization and consumer logic.
Persisting raw uploads expands privacy and retention obligations. Passing only
a registry identifier into saved receipts breaks portable reproduction.

Bounded in-memory inspection plus embedded checkpoints avoids those dependencies.
Large captures must use existing operator-controlled CLI/research tools rather
than silently bypassing the browser's limits. Early prefixes may lack usable
option rows and must report an unavailable checkpoint. The current-build study
uses synthetic fixtures; qualification of a user's data and observed usability
remain separate gates.
