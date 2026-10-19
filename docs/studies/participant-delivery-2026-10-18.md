# Guided Intake Participant Delivery — 2026-10-18

This is a delivery amendment prepared before participant collection. It does
not replace the [frozen guided-intake study](guided-intake-2026-10-18.md) or
change GI-01–GI-06, scoring, application, dependencies or synthetic inputs.
[Study Recruitment](../study-recruitment.md) owns the distribution procedure.

| Identity | Recorded value |
| --- | --- |
| Parent cohort | `guided-intake-2026-10-18-r1` |
| Delivery revision | `guided-intake-2026-10-18-r1-participant-v1` |
| Application source | `0ddfbc4c0d94dd09935590ccb00db5d980863151` |
| Source tree | `92aa7af9f670801c563ee256c09764bc12cde8d8` |
| Application version | `0.6.0` |
| Wheel SHA-256 | `f1d5aa236d69a1c1d6514e6a5bf98d38a736bd28a6469ed2dd10057b573f0fc6` |
| Dependency lock SHA-256 | `11c4004356ffda2ad03fc5378b31694453b419c1543054d35cea124a8ba34ec1` |
| Rehearsed runtime | CPython 3.12.13, Apple Silicon macOS |
| Observed participants / invitations / bookings | `0 / 0 / 0` at preparation |
| Planned slots | Six, three ES and three NQ; actual records blank |

## Saved artifacts

Artifacts remain under ignored
`dist/recruitment/guided-intake-2026-10-18-r1/`. This record preserves their
identities; generated binaries and private participant records do not enter Git.

| Artifact | Files | Bytes | SHA-256 |
| --- | ---: | ---: | --- |
| `gex-participant-package-v1.zip` | 20 | 1,863,171 | `41048fa1cbafa323c00132f762fde343360d8a02637cb0ae75fd9066233d6d9f` |
| `gex-organizer-pack-v1.zip` | 9 | 19,385 | `931a7fd4d8c0963090288e538c309e1905092563926cb14d48e7e2e482235bc5` |
| Participant `consent.pdf` | — | — | `91d1d2d9200f29fe1ac5918f42281a13e66fd927615e80a0becb0978037ca2f0` |

The participant ZIP includes the exact wheel, lock, task guide, license and two
captures; nine user-help pages; a limited public build manifest; start
instructions; blank consent PDF/text; and an exact SHA-256 inventory. It omits
moderator guides, scorecards, answer keys, protocol/scoring internals, rehearsal
results, maintainer evidence and the source archive. The organizer ZIP contains
the invitation, confirmation, reminder, checklist, planned session CSV, start
guide, blank consent PDF/text and inventory.

The full parent kit's 86 inventoried files (plus `SHA256SUMS`) were reread and
verified unchanged. Its
ZIP remains `f8eec28e3d2524bd01664b6e21999b5abe2e93c39c1189a64237e863142010d5`;
its inventory file remains
`986d2f659e4887d29e27b44f3ffd0c223d1144bc252c805a9a427e89bee5a5eb`.
The September kit remains a separate historical cohort.

## Amendment and verification

Five links to omitted maintainer documents were rendered as plain text in three
help pages: First Run (Study Build, Contributing, Application Review), Wind
Tunnel (GEX-WIND-001), and Model Assumptions (Model Validation). The other six
help pages are byte-identical. `qa/delivery-amendment.json` records every
original/delivered help hash and unchanged application/input hash. Task text
and scoring remain unchanged. Use this delivery revision for all six sessions
and disclose the amendment in study reporting.

Direct saved-artifact checks verified inventories and ZIP entry bytes, all
18 remaining local help links/anchors, the excluded-material boundary and
absence of private maintainer paths. Negative checks rejected an extra
moderator file, symlink, changed task guide and broken local help link.
Consent verification checked two pages, 15 fields, initially unselected choices,
only required observation, independent optional recording/AI choices, field
bounds and a fill/readback round trip without changing the blank source. Both
final rendered pages were visually reviewed for clipping and overlap.
`qa/summary.json` records this preparation evidence.

This evidence establishes packaging and form behavior, not participant consent,
recruitment success, customer acceptance, legal review or live-provider
certification. Contact/reviewer details, dates, incentive terms and distribution
links still require the organizer's private completion. The invitation is a
template for the owner to send. Issue #4 remains open for actual Tradovate
payloads.
