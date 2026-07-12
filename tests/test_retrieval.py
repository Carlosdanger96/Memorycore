from types import SimpleNamespace

from memorycore.retrieval import build_fts_query, rank_memories, render_context


def test_build_fts_query_ignores_operator_punctuation():
    assert build_fts_query('SQLite OR "graph"') == '"SQLite" AND "OR" AND "graph"'
    assert build_fts_query("   ") == ""


def test_render_context():
    text = render_context([{"id": "m1", "memory_type": "fact",
        "summary": "A summary", "content": "Full content"}])
    assert "[fact:m1] A summary" in text
    assert "Full content" in text


def test_rank_prefers_exact_match_over_memory_type():
    note = SimpleNamespace(id="n", memory_type="note", content="Use SQLite", summary=None, tags=[], confidence=None, updated_at="2026-01-01T00:00:00+00:00")
    decision = SimpleNamespace(id="d", memory_type="decision", content="Use another store", summary=None, tags=[], confidence=1, updated_at="2026-01-01T00:00:00+00:00")
    ranked = rank_memories("use sqlite", [decision, note], 2)
    assert ranked[0].memory.id == "n"
    assert "exact_content_match" in ranked[0].reasons
