"""Display-only learning material. Never an assessment or a grading-key projection."""
from contracts.models import Flashcard


def demo_flashcards() -> list[Flashcard]:
    notes = [
        ("bfs", "What order does breadth-first search explore?",
         "It explores by depth: all nodes one edge away, then two edges away, and so on. With equal edge costs, this finds a shortest path."),
        ("ucs", "How does uniform-cost search choose its next node?",
         "It expands the frontier node with the lowest accumulated path cost g(n). Unlike breadth-first search, it accounts for different edge costs."),
        ("astar", "What does A* combine in its priority f(n)?",
         "f(n) = g(n) + h(n): the cost already paid to reach a node, plus an estimate of the remaining cost to a goal."),
        ("admissibility", "What does it mean for a heuristic to be admissible?",
         "At every node, its estimate is no greater than the actual cheapest remaining path cost: h(n) ≤ h*(n)."),
        ("consistency", "What local check defines a consistent heuristic?",
         "For every edge n → n′, h(n) ≤ c(n,n′) + h(n′). The estimate cannot drop by more than the cost of that step."),
        ("admissibility_vs_consistency", "How are consistency and admissibility connected?",
         "With nonnegative edge costs and h(goal)=0, consistency implies admissibility. An admissible heuristic can still violate consistency on an edge."),
        ("admissibility_vs_consistency", "How would you check both properties on a small graph?",
         "First compute the cheapest remaining cost at each node and compare each estimate with that cost. Then check the consistency inequality separately on every edge."),
        ("astar", "What happens when A* uses h(n)=0 everywhere?",
         "Its priority becomes g(n), so it orders the frontier like uniform-cost search. The zero heuristic is admissible and consistent for nonnegative edge costs."),
    ]
    return [Flashcard(card_id=f"demo-card-{i}", concept_id=concept, front=front,
                      back=back, source="Intro AI · study notes")
            for i, (concept, front, back) in enumerate(notes, 1)]


def course_flashcards(course) -> list[Flashcard]:
    # Explicitly publish concept summaries for studying; do not serialize private
    # question records, rubrics, answer keys, provider prompts or whole sources.
    filenames = {chunk.chunk_id: material.filename
                 for material in course.materials for chunk in material.chunks}
    return [Flashcard(card_id=f"{concept.concept_id}-recall", concept_id=concept.concept_id,
                      front=f"What are the key ideas in {concept.name}?", back=concept.summary,
                      source=" · ".join(dict.fromkeys(filenames[ref.chunk_id]
                                         for ref in concept.source_refs)))
            for concept in course.concepts]
