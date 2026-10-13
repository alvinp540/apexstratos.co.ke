# Tutorial Content Operations

## Schedule

The initial fixed schedule is defined by `apps/cohorts/tutorial_schedule.py`: 10 capability fields, months 1-2, four weeks per month, Monday-Thursday, and two slots per field/day. That defines 640 tutorial slots and 3,200 questions. The database allows month indices after month 2 without a schema change.

Tutorial schedule coordinates are unique per field, month, week, day and daily slot. Uploading or reading content never deletes a tutorial or question.

## Create and Publish

Use the Django admin Tutorial form to create a Draft, upload its ApexStratos-owned video, set its schedule, objectives and difficulty, and author every teaching section. Add exactly five questions in order 1-5 in the inline question form. Correct answers and rationales are available only to admin users; the student API omits both.

The structured lesson sections cover concept explanation, terminology/components, why it matters, how it works, worked examples, common mistakes, practical application, decisions/trade-offs, and connections. Pair the two daily slots so that the second extends or applies the first. Do not use generic randomized questions or copied placeholder video clips.

Use the admin actions in sequence:

1. Draft to In Review: requires an uploaded video, all teaching sections, three or more objectives, and exactly questions 1-5.
2. In Review to Approved: Medical & Health and Law & Society also require an admin attestation that appropriate expert review occurred.
3. Approved to Published: rechecks publish requirements and exposes the tutorial only when `scheduled_for` is reached.
4. Published to Archived: removes it from student discovery without deleting its record or attempts.

Editing a tutorial in the admin returns it to Draft, so changes cannot silently replace reviewed live content.

## One-Click Daily Upload

In Django Admin, open **Tutorials** and click **Upload tutorials for a day**. Choose month, week, weekday, schedule time, and one ZIP file. The ZIP must contain exactly `manifest.json` and 20 distinct internal MP4 files beneath `videos/`.

The JSON manifest has this structure (the text below is an abbreviated shape, not lesson content; every section must contain substantive, field-specific teaching):

```json
{
	"tutorials": [
		{
			"field": "Software Development",
			"daily_slot": 1,
			"title": "A descriptive field-specific lesson title",
			"description": "What the practitioner will understand and apply",
			"learning_objectives": ["Explain", "Apply", "Reason"],
			"difficulty": "foundation",
			"duration_minutes": 20,
			"video_path": "videos/software-development-1.mp4",
			"concept_explanation": "Authored lesson section",
			"terminology_and_components": "Authored lesson section",
			"why_it_matters": "Authored lesson section",
			"how_it_works": "Authored lesson section",
			"worked_examples": "Authored lesson section",
			"common_mistakes": "Authored lesson section",
			"practical_application": "Authored lesson section",
			"decisions_and_tradeoffs": "Authored lesson section",
			"related_concepts": "Authored lesson section",
			"questions": [
				{
					"order": 1,
					"question_type": "multiple_choice",
					"prompt": "A practical scenario question connected to this lesson...",
					"options": ["Option A", "Option B", "Option C"],
					"correct_answer": "Option A",
					"rationale": "Why this response best follows the taught reasoning"
				}
			]
		}
	]
}
```

Include two complementary records for each of the ten exact capability-field names and five questions per record, numbered 1 through 5. All 20 video paths must be distinct. The uploader validates the complete day before creating any records, enforces a 1.5 GB ZIP cap and 300 MB per video, verifies MP4 signatures, and refuses a duplicate schedule day. A valid upload creates Drafts only; it does not approve or publish content.

For the first admin account, run `python manage.py setup_founder_admin` in a trusted backend terminal and enter a newly rotated password at the hidden prompts. This updates/creates the founder email and username as configured by that command; the password is never a command-line argument or stored in the repository. Rotate any credentials that have been pasted into chat before doing this.

## Initial Library Verification

Run from `apex_backend` after applying migrations and uploading actual content:

```powershell
python manage.py audit_initial_tutorial_library --settings=apex_backend.settings.development
```

The command checks published tutorial records, uploaded internal video references, and question totals for months 1-2. It fails until the actual 640 videos and 3,200 authored questions are present. It does not generate lessons, questions, or video placeholders.
