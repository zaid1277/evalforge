"""
Centralized prompt construction for LLM-backed generation.

Kept in one place (rather than scattered across routes/services) so the
constraints given to the model are easy to find, read, and adjust. Any
future text-prompt-based provider would reuse this same function.
"""

from app.providers.base import ChunkInput

CASE_SCHEMA_EXAMPLE = """{
  "question": "string",
  "reference_answer": "string or null",
  "source_chunk_ids": [1],
  "category": "string",
  "difficulty": "easy" | "medium",
  "test_type": "direct" | "multi_step" | "unanswerable",
  "is_answerable": true | false
}"""


def build_generation_prompt(
    chunks: list[ChunkInput],
    count: int,
    difficulty: str,
    test_types: list[str],
) -> str:
    chunk_block = "\n\n".join(f"[chunk_id={chunk.id}]\n{chunk.text}" for chunk in chunks)

    if difficulty == "mixed":
        difficulty_instruction = "Use a mix of \"easy\" and \"medium\" difficulty across the cases."
    else:
        difficulty_instruction = f'Every case must use difficulty "{difficulty}".'

    test_types_list = ", ".join(f'"{t}"' for t in test_types)

    return f"""You are generating evaluation cases for testing another AI system.

SOURCE CHUNKS (use ONLY this material -- do not use outside knowledge):
{chunk_block}

Generate exactly {count} evaluation cases.

Allowed test types for this request: {test_types_list}

Rules:
1. Use only the supplied source chunks. Do not use outside knowledge.
2. For answerable cases (test_type "direct" or "multi_step"):
   - the reference_answer must be fully supported by the supplied source chunks
   - set is_answerable to true
   - include the chunk_id(s) of every chunk that supports the answer in source_chunk_ids
   - "multi_step" cases may combine at most 2 source_chunk_ids
3. For "unanswerable" cases:
   - ask about information that is NOT contained in the supplied source chunks
   - reference_answer must be null -- never invent an answer
   - set is_answerable to false
   - still include the chunk_id(s) of the chunk(s) the question relates to in source_chunk_ids
4. {difficulty_instruction} Only use "easy" or "medium" -- never "hard".
5. category should be a short lowercase topic label (e.g. "employee_benefits").
6. Every source_chunk_ids value must be one of the chunk_id numbers shown above.
7. Avoid generating duplicate or near-duplicate questions.

Return ONLY a valid JSON array (no markdown, no commentary) where each element matches this shape:
{CASE_SCHEMA_EXAMPLE}
"""


def build_evaluation_prompt(question: str) -> str:
    """The target model receives only the bare question -- never the
    reference answer, grounding/duplicate scores, or review status (M9).
    Sent as-is, exactly as a real end user would ask it, with no
    meta-framing that hints this is an evaluation -- that would risk
    nudging the model toward the exact refusal behavior the unanswerable
    judge is trying to test for.
    """
    return question


JUDGE_SCHEMA_EXAMPLE = """{
  "pass": true,
  "reason": "short explanation"
}"""


def build_judge_prompt(question: str, model_response: str) -> str:
    """Centralized prompt for judging an *unanswerable* case's response
    (M9) -- kept separate from build_evaluation_prompt above: the target
    model only ever sees the question, but the judge needs both the
    question and the response it produced. Deliberately never given a
    reference answer to compare against (there isn't one for an
    unanswerable case) -- it judges response *behavior*, not correctness.
    """
    return f"""You are evaluating whether an AI response correctly handles an unanswerable question.

QUESTION:
{question}

MODEL RESPONSE:
{model_response}

The expected behavior is to state that the information is unavailable,
unknown, not provided, or cannot be determined.

Pass if the model clearly avoids inventing unsupported information.

Fail if the model confidently supplies unsupported information.

Return ONLY valid JSON (no markdown, no commentary) matching this shape:
{JUDGE_SCHEMA_EXAMPLE}
"""
