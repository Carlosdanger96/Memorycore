from memorycore.retrieval import build_fts_query, render_context


def test_build_fts_query_ignores_operator_punctuation():
    """Test that FTS query building handles operator punctuation correctly."""
    # The order of tokens may vary, but the content should be the same
    result = build_fts_query('SQLite OR "graph"')
    tokens = set(result.split(' AND '))
    expected_tokens = {'"SQLite"', '"OR"', '"graph"'}
    assert tokens == expected_tokens
    assert build_fts_query("   ") == ""


def test_render_context():
    """Test context rendering."""
    text = render_context([{"id": "m1", "memory_type": "fact",
        "summary": "A summary", "content": "Full content"}])
    assert "[fact:m1] A summary" in text
    assert "Full content" in text


def test_build_fts_query_with_phrases():
    """Test FTS query building with quoted phrases."""
    result = build_fts_query('"hello world" test')
    tokens = set(result.split(' AND '))
    expected_tokens = {'"hello"', '"world"', '"test"'}
    assert tokens == expected_tokens


def test_build_fts_query_single_token():
    """Test FTS query building with single token."""
    result = build_fts_query("single")
    assert result == '"single"'


def test_render_context_with_metadata():
    """Test context rendering with metadata."""
    text = render_context([
        {
            "id": "m1",
            "memory_type": "fact",
            "summary": "A summary",
            "content": "Full content",
            "metadata": {"key": "value"}
        }
    ], include_metadata=True)
    assert "[fact:m1] A summary" in text
    assert "Full content" in text
    assert "Metadata:" in text


def test_render_context_max_length():
    """Test context rendering with max content length."""
    long_content = "A" * 1000
    text = render_context([
        {
            "id": "m1",
            "memory_type": "fact",
            "summary": "Long content",
            "content": long_content
        }
    ], max_content_length=100)
    assert "..." in text
    assert len(text.split('\n')[1]) <= 103  # 100 + "..."
