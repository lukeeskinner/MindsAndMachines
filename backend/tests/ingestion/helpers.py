"""Mock provider plans; no model or network calls."""
from backend.app.ingestion.passages import build_passages


def plan_for(materials):
    concepts, names = [], set()
    for passage in build_passages(materials):
        if passage.label.casefold() in names:
            continue
        names.add(passage.label.casefold())
        concepts.append({"passage_id": passage.passage_id, "first_question":
            {"prompt": "Which statement is supported by this passage?",
             "answer_id": passage.answers[0][0],
             "wrong_option_1": "This material describes interstellar cheese production.",
             "wrong_option_2": "This material explains lunar railway schedules.",
             "wrong_option_3": "This material is about rainbow crop rotation."},
            "second_question": {"prompt": "Which statement would accurately summarize the source?",
             "answer_id": passage.answers[-1][0],
             "wrong_option_1": "This material concerns underwater marmalade factories.",
             "wrong_option_2": "This material explains lunar railway schedules.",
             "wrong_option_3": "This material is about rainbow crop rotation."},
            "additional_questions": [],
        })
        if len(concepts) == 5:
            break
    for i in range(max(0, 5 - len(concepts) * 2)):
        concept = concepts[i % len(concepts)]
        concept["additional_questions"].append({**concept["first_question"],
            "prompt": f"Which source statement supports recall task {i + 1}?"})
    return {"concepts": concepts}
