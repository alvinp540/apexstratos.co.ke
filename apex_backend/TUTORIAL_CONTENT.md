# ApexStratos Question-Library Operations

## Programme targets

| Library | Initial assessments | Questions per assessment | Initial questions | Student price |
|---|---:|---:|---:|---|
| Tutorial Library | 640 | 10 | 6,400 | Free |
| Sponsored View Library | 800 | 10 | 8,000 | KSh 20 per attempt |
| Main Contest Library | 720 | 10 | 7,200 | KSh 100 per applicable access period |
| **Total** | **2,160** | **10** | **21,600** | Programme-specific |

These are target quantities, not live counts. Only complete, reviewed database records should be represented as available. Run `python manage.py audit_apexstratos_inventory` to report actual complete inventory and shortfalls. The current local database audit found 0/640 Tutorials, 0/800 Sponsored View assessments, and 0/720 Main Contest assessments (zero complete questions in each library).

## Question-first content

These programmes use structured written instruction, worked examples, MCQs, explanations, and optional written reasoning. There is no video playback, video upload, media approval, or external media-service dependency.

Each published assessment must contain exactly ten ordered multiple-choice questions, numbered 1 through 10. Each question must have exactly four distinct answer options, a correct answer that exactly matches one option, and a written rationale explaining the correct reasoning. Student APIs withhold answer keys and rationales until the attempt is submitted and graded.

Tutorial lessons also require the structured written teaching sections and at least three learning objectives. Medical and Health and Law and Society content requires administrator-recorded expert review before approval.

## Administration

Administrators can create additional tutorials in Django Admin, add ten questions in the question inline, and use the review/approval/scheduling/publication actions. Main Contest assessments can also be added in Django Admin and require a 20-minute duration, at least three learning objectives, and ten valid questions. Historical records with attempts are protected from editing/deletion; new content is added as separate records.

For reviewed source packs, use `python manage.py import_apexstratos_assessments --library tutorials --file <pack.json>`, `--library sponsored-view`, or `--library main-contest`. A run without `--apply` is a validation-only dry run. Applying a valid pack appends deterministic, provenance-tracked draft records; it never updates a previously imported version. Reimporting unchanged external IDs skips those records; changed data under an existing ID fails and requires a new external ID. The importer requires provenance, official study areas, eight-week schedule coordinates, exactly ten distinct MCQs, four distinct answer options, a matching answer key, and a non-empty rationale for every question. Drafts must still pass the existing publication review workflow.

Tutorial schedule coordinates use `month` and local `week` values (weeks 1–4 in each month). Student library filters expose the combined initial Week 1–8 sequence. Main contest availability remains controlled by the published Friday–Sunday schedule and server-side attempt rules; library browsing does not grant access.

## Weekly access and attempt timing

The backend is authoritative for the weekly calendar and uses the `Africa/Nairobi` timezone. Tutorial and Sponsored View start windows are Monday 00:00 through Friday 00:00 EAT; Main Contest starts are permitted Friday 00:00 through Monday 00:00 EAT. Boundaries are exclusive at the closing instant. Students may start at any time inside an open window; `scheduled_for` is not an individual appointment or release time.

The Main Contest's 20-minute timer begins when the server creates the attempt. The server returns the start time and deadline, preserves saved answers on resume, and rejects saves or submissions at/after the deadline. Attempts cannot outlast their activity's weekly window. Tutorial, Sponsored View, and Main Contest start endpoints enforce their windows independently of the frontend. Sponsored View requires an administrator-verified KSh 20 payment per attempt and enforces a maximum of five paid attempts per student per EAT calendar day, Monday–Thursday. The schedule endpoint reports current availability and the next opening period.

## Content status

The local development database was backed up before applying the new schema migrations, then audited. It contains zero complete assessments and zero questions in all three required libraries. No approved question-content corpus for the required 2,160 assessments was present in the repository. The only bundled question seeder found creates a legacy cohort assessment outside these libraries and does not contain a provenance-backed programme corpus. The platform must not seed fictional questions or advertise target quantities as if they were populated. The repeatable importer is a safe intake path, not a substitute for authoring, licensing, subject-matter review, or obtaining the actual content. Import or author reviewed content before declaring the libraries complete.
