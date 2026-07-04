from memorycore.retrieval import build_fts_query, render_context


def test_build_fts_query_ignores_operator_punctuation():
    assert build_fts_query('SQLite OR "graph"') == '"SQLite" AND "OR" AND "graph"'
    assert build_fts_query("   ") == ""


def test_render_context():
    text = render_context([{"id": "m1", "memory_type": "fact",
        "summary": "A summary", "content": "Full content"}])
    assert "[fact:m1] A summary" in text
    assert "Full content" in text
