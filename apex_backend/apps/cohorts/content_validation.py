import hashlib
import json
import re

from .tutorial_schedule import CAPABILITY_FIELDS


PLACEHOLDER_TERMS = re.compile(
    r'\b(?:lorem ipsum|placeholder|coming soon|tbd|todo|sample question|question text here)\b',
    re.IGNORECASE,
)
TUTORIAL_TEACHING_FIELDS = (
    'concept_explanation',
    'terminology_and_components',
    'why_it_matters',
    'how_it_works',
    'worked_examples',
    'common_mistakes',
    'practical_application',
    'decisions_and_tradeoffs',
    'related_concepts',
)


def _has_placeholder(value):
    if isinstance(value, str):
        return bool(PLACEHOLDER_TERMS.search(value))
    if isinstance(value, list):
        return any(_has_placeholder(item) for item in value)
    return False


def question_set_is_complete(questions):
    if len(questions) != 10 or [question.order for question in questions] != list(range(1, 11)):
        return False
    prompts = set()
    for question in questions:
        prompt = ' '.join(question.prompt.casefold().split())
        options = question.options
        if (
            getattr(question, 'question_type', 'multiple_choice') != 'multiple_choice'
            or not prompt
            or prompt in prompts
            or not isinstance(options, list)
            or len(options) != 4
            or any(not isinstance(option, str) or not option.strip() for option in options)
            or len({option.casefold().strip() for option in options}) != 4
            or not isinstance(question.correct_answer, str)
            or question.correct_answer not in options
            or not isinstance(question.rationale, str)
            or not question.rationale.strip()
            or _has_placeholder(question.prompt)
            or _has_placeholder(options)
            or _has_placeholder(question.rationale)
        ):
            return False
        prompts.add(prompt)
    return True


def assessment_fingerprint(questions):
    normalized_questions = [
            {
                'prompt': ' '.join(question.prompt.casefold().split()),
                'options': sorted(' '.join(option.casefold().split()) for option in question.options),
                'answer': ' '.join(question.correct_answer.casefold().split()),
            }
            for question in questions
        ]
    content = {'questions': sorted(normalized_questions, key=lambda question: question['prompt'])}
    encoded = json.dumps(content, ensure_ascii=True, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def tutorial_is_complete(tutorial):
    questions = list(tutorial.questions.order_by('order'))
    if (
        tutorial.field not in CAPABILITY_FIELDS
        or not tutorial.title.strip()
        or _has_placeholder(tutorial.title)
        or not tutorial.description.strip()
        or _has_placeholder(tutorial.description)
        or not isinstance(tutorial.learning_objectives, list)
        or len(tutorial.learning_objectives) < 3
        or not all(
            isinstance(objective, str)
            and objective.strip()
            and not _has_placeholder(objective)
            for objective in tutorial.learning_objectives
        )
        or not all(
            isinstance(getattr(tutorial, field), str)
            and getattr(tutorial, field).strip()
            and not _has_placeholder(getattr(tutorial, field))
            for field in TUTORIAL_TEACHING_FIELDS
        )
        or (
            tutorial.field in {'Medical and Health', 'Law and Society'}
            and not tutorial.expert_reviewed
        )
        or not question_set_is_complete(questions)
    ):
        return None
    return assessment_fingerprint(questions)


def contest_is_complete(assessment):
    questions = list(assessment.questions.order_by('order'))
    if (
        assessment.field not in CAPABILITY_FIELDS
        or not assessment.title.strip()
        or _has_placeholder(assessment.title)
        or assessment.duration_minutes != 20
        or not isinstance(assessment.learning_objectives, list)
        or len(assessment.learning_objectives) < 3
        or not all(
            isinstance(objective, str)
            and objective.strip()
            and not _has_placeholder(objective)
            for objective in assessment.learning_objectives
        )
        or not assessment.description.strip()
        or _has_placeholder(assessment.description)
        or (
            assessment.field in {'Medical and Health', 'Law and Society'}
            and not assessment.expert_reviewed
        )
        or not question_set_is_complete(questions)
    ):
        return None
    return assessment_fingerprint(questions)


def sponsored_view_is_complete(assessment):
    questions = list(assessment.questions.order_by('order'))
    if (
        assessment.field not in CAPABILITY_FIELDS
        or not assessment.title.strip()
        or _has_placeholder(assessment.title)
        or not assessment.description.strip()
        or _has_placeholder(assessment.description)
        or not isinstance(assessment.learning_objectives, list)
        or len(assessment.learning_objectives) < 3
        or not all(
            isinstance(objective, str)
            and objective.strip()
            and not _has_placeholder(objective)
            for objective in assessment.learning_objectives
        )
        or (
            assessment.field in {'Medical and Health', 'Law and Society'}
            and not assessment.expert_reviewed
        )
        or not question_set_is_complete(questions)
    ):
        return None
    return assessment_fingerprint(questions)
