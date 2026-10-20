# Study Recruitment And Participant Delivery

Use this procedure to recruit and schedule the six observed offline sessions.
[Product Validation](product-validation.md) owns participant selection, consent,
tasks and scoring. [Study Build](study-build.md) owns the frozen application and
full moderator kit. The [October 18 delivery record](studies/participant-delivery-2026-10-18.md)
binds the participant-only amendment to that kit. Preparation has produced no
participant observations, invitations or bookings.

This is the frozen October 18 cohort procedure. Later pricing, saved-session,
model-comparison, and display changes do not replace its wheel, protocol, or
materials. Use [First Run](first-run.md) and [Wind Tunnel](wind-tunnel.md) for
the current application; a study of that newer application needs a separately
reviewed build/cohort identity under [Study Build](study-build.md).

## Prepare the owner copy

The reusable blank sources are in [study-kit/recruitment](study-kit/recruitment/START-HERE.md):
an invitation, confirmation, reminder, organizer checklist, six-slot plan,
participant start instructions and consent text. Generated archives and PDFs
stay under ignored `dist/`; completed study records belong in private
owner-controlled storage outside the repository and shared kits.

For the prepared cohort, use the already verified files under
`dist/recruitment/guided-intake-2026-10-18-r1/`. Send
`gex-participant-package-v1.zip` and its reviewed checksum. Retain
`gex-organizer-pack-v1.zip` privately for recruitment. The full 86-file study ZIP
contains moderator guidance, scoring, answers and rehearsal evidence; keep it
with the moderator. The participant ZIP has 20 files and excludes those items.

Copy organizer materials into private storage before entering anyone's details.
Fill in the study contact, authorized reviewers, appointment windows and time
zone, incentive and early-stop terms (or explicitly no incentive), participant
ZIP and meeting links, and a calendar date for deleting private study records.
Set a removal-request deadline no later than that deletion date. Verify links
from the recipient's access level.

Personalize the consent form separately and give participants a copy. It
supersedes the blank template in the original ZIP; leave that ZIP unchanged.
Observation consent is required before tasks. Audio recording, shared-window
recording and ChatGPT/OpenAI analysis of de-identified written notes each need
their own explicit Yes. Blank or No gives no permission. A note-only, manually
analyzed session remains available. Keep cameras and automatic transcription
off. AI analysis excludes names, contact details, audio, video and full
transcripts. Share only the relevant application window.

## Recruit and run the sessions

Send the invitation yourself. Ask for role, relevant experience, OS/chip,
Python availability, time zone and availability windows. The rehearsed setup
is Apple Silicon with Python 3.12.13; record differences and agree on a suitable
environment. Leave installation for the observed task. Preinstallation cannot
count as unaided observed installation.

Use the six blank planned slots P01–P06, with three ES and three NQ assignments.
The CSV records proposed assignments only. Keep actual consent, schedules,
identity mappings and observations privately; record changes, assistance,
failures, refusals, withdrawals, no-shows and non-starts. Run the frozen
GI-01–GI-06 tasks and scoring without redefining success during the cohort.
Record contributor relationships when assessing independence.

Honor withdrawal and the stated deadlines. Deletion covers every organizer-held
private copy: contact/scheduling messages, consent, ID links, individual notes
and recordings. Completed consent and messages also link names to IDs; deleting
only a mapping table is insufficient. Findings without participant identifiers
may remain. Do not add real people or completed records to Git or generated
handoff folders.

## Rebuild from tracked sources

The participant builder validates the frozen parent's exact inventory and copies
only allowlisted participant materials. It preserves the wheel, dependency
lock, captures and task guide; omitted maintainer links in help become plain
text, with before/after hashes recorded in the delivery amendment.

```bash
python scripts/build_participant_delivery.py \
  --frozen-kit dist/study/guided-intake-2026-10-18-r1 \
  --consent-pdf /path/to/reviewed-blank-consent.pdf \
  --delivery-id guided-intake-2026-10-18-r1-participant-v1 \
  --output dist/recruitment/NEW_DELIVERY_DIRECTORY
```

The committed templates and PDF source describe the October cohort's
participant-v1 revision. The builder supports that identity only; another
cohort or delivery revision needs reviewed source/form amendments first.
Use a new output directory; the builder refuses replacement. It records file
inventories, archive checksums and the amendment. The PDF is a separately
reviewed input: copying it does not establish its content, blank form state or
consent semantics. Review its text, fields, filling behavior and rendered pages
before delivery. Hashes detect changed bytes; deliver the reviewed checksum
through a trusted channel.

The optional [consent generator](../scripts/build_study_consent.py) preserves the
two-page form source and needs ReportLab and pypdf in a contributor environment:

```bash
python scripts/build_study_consent.py --output /path/to/new-blank-consent.pdf
```

PDF metadata and ZIP metadata may differ between builds. Compare file contents
and record new hashes; do not claim byte-identical archives or replace the
recorded participant-v1 delivery. Use one reviewed delivery revision for all six
sessions. Disclose packaging amendments in reporting. Changes to application,
dependencies, fixtures, task text or scoring need a new cohort/build identity.
