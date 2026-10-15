# ApexStratos Question-Library Operations

## Programme targets

| Library | Initial assessments | Questions per assessment | Initial questions | Student price |
|---|---:|---:|---:|---|
| Tutorial Library | 640 | 10 | 6,400 | Free |
| Sponsored View Library | 800 | 10 | 8,000 | KSh 20 per attempt |
| Main Contest Library | 720 | 10 | 7,200 | KSh 100 per applicable access period |
| **Total** | **2,160** | **10** | **21,600** | Programme-specific |

These are target quantities, not live counts. Only complete, reviewed database records should be represented as available. Run `python manage.py audit_apexstratos_inventory --settings=apex_backend.settings.development` to report actual complete inventory and shortfalls. Sponsored View has no assessment, payment, attempt, or reward models in the current backend; its reported initial inventory is zero until those workflows are implemented.

## Question-first content

These programmes use structured written instruction, worked examples, MCQs, explanations, and optional written reasoning. There is no video playback, video upload, media approval, or external media-service dependency.

Each published assessment must contain exactly ten ordered multiple-choice questions, numbered 1 through 10. Each question must have at least two answer options and a correct answer that exactly matches one option. Add a written rationale explaining the correct reasoning; the student API withholds answer keys and rationales until a tutorial attempt is submitted.

Tutorial lessons also require the structured written teaching sections and at least three learning objectives. Medical and Health and Law and Society content requires administrator-recorded expert review before approval.

## Administration

Administrators can create additional tutorials in Django Admin, add ten questions in the question inline, and use the review/approval/scheduling/publication actions. Main Contest assessments can also be added in Django Admin and require a 20-minute duration, at least three learning objectives, and ten valid questions. Historical records with attempts are protected from editing/deletion; new content is added as separate records.

Tutorial schedule coordinates use `month` and local `week` values (weeks 1–4 in each month). Student library filters expose the combined initial Week 1–8 sequence. Main contest availability remains controlled by the published Friday–Sunday schedule and server-side attempt rules; library browsing does not grant access.

## Weekly access and attempt timing

The backend is authoritative for the weekly calendar and uses the `Africa/Nairobi` timezone. Tutorial and Sponsored View start windows are Monday 00:00 through Friday 00:00 EAT; Main Contest starts are permitted Friday 00:00 through Monday 00:00 EAT. Boundaries are exclusive at the closing instant. Students may start at any time inside an open window; `scheduled_for` is not an individual appointment or release time.

An attempt timer begins when the server creates the attempt. The server returns the start time and deadline, preserves saved answers on resume, and rejects saves or submissions at/after the deadline. An attempt cannot outlast its activity's weekly window. Tutorial and Main Contest start endpoints enforce their windows independently of the frontend. The schedule endpoint reports current availability and the next opening period. Sponsored View follows the same published Monday–Thursday window, but remains non-startable until its backend assessment, payment, and attempt workflows are implemented.

## Content status

The local development database was audited read-only during implementation. It contained zero Tutorial records and zero Main Contest records. No approved question-content corpus for the required 2,160 assessments was present in the repository. The legacy video-placeholder seeding commands were removed; the platform must not seed fictional questions or advertise target quantities as if they were populated. Import or author reviewed content before declaring the libraries complete.
