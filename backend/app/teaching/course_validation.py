"""Conservative presentation edits over selected course prose, not arbitrary NLI."""
import re

from backend.app.ingestion.models import normalized
from backend.app.ingestion.teaching import PROCESS_TEMPLATES, contains_phrase


# Explicitly reviewed rewordings of the neutral process instructions. Subject
# facts have no automatic synonym substitution: that could reverse a claim.
_PROCESS_REWORDINGS = {
    PROCESS_TEMPLATES["diagnostic_probe"][0]: (
        "Which detail in the passage helps you respond to the task?",
        "What detail from the material would you use here?",
    ),
    PROCESS_TEMPLATES["socratic_hint"][0]: (
        "Find the condition or relationship in the passage. Which part of the task relies on it?",
        "Look for a condition or relationship in the passage. How does it connect to the task?",
    ),
    PROCESS_TEMPLATES["worked_example"][0]: (
        "First, find what the task asks you to look for.",
        "Start by identifying what the task asks you to find.",
    ),
    PROCESS_TEMPLATES["worked_example"][1]: (
        "Find the matching passage. Separate the condition from what happens as a result.",
        "Next, separate the passage's condition from its consequence.",
    ),
    PROCESS_TEMPLATES["worked_example"][2]: (
        "Compare each possible response with that relationship. Leave out claims the passage does not support.",
        "Finally, compare the responses with that relationship and rule out unsupported claims.",
    ),
}


def sentences(text: str) -> tuple[str, ...]:
    # Complete sentences only: accepting arbitrary source substrings could drop
    # a negation or detach a qualification. Not a general sentence parser.
    return tuple(re.split(r"(?<=[.!?])\s+", normalized(text)))


def allowed_sentences(paragraphs: tuple[str, ...]) -> tuple[str, ...]:
    allowed = []
    for paragraph in paragraphs:
        for wording in (paragraph, *_PROCESS_REWORDINGS.get(paragraph, ())):
            allowed.extend(sentences(wording))
    return tuple(dict.fromkeys(allowed))


def validate_personalization(prose: str, allowed: tuple[str, ...], private_answers: tuple[str, ...]) -> None:
    if any(contains_phrase(prose, answer) for answer in private_answers):
        raise ValueError("Teaching reveals a solution instead of prompting the learner")
    basis = {normalized(sentence).casefold() for sentence in allowed}
    if any(sentence.casefold() not in basis for sentence in sentences(prose)):
        raise ValueError("Teaching exceeds the selected course content basis")
