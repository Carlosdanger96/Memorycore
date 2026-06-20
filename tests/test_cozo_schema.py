"""Test CozoDB schema loading and validation."""

import pytest
import os
import tempfile
from pathlib import Path


def test_cozo_schema_parsing():
    """Test that the Cozo schema can be parsed without syntax errors."""
    schema_path = Path(__file__).parent.parent / "cozodb" / "schema.cozo"
    
    # Check that the schema file exists
    assert schema_path.exists(), f"Schema file not found: {schema_path}"
    
    # Read the schema content
    schema_content = schema_path.read_text()
    
    # Check for common syntax errors (git merge conflict markers)
    assert ">>>>>>>" not in schema_content, "Merge conflict markers found in schema"
    assert "<<<<<<<" not in schema_content, "Merge conflict markers found in schema"
    # Note: "=======" is allowed as it's used for section headers in Cozo
    
    # Check that the schema has the expected structure
    assert "?memories[" in schema_content, "Memories table not found"
    assert "?projects[" in schema_content, "Projects table not found"
    assert "?memory_links[" in schema_content, "Memory links table not found"
    
    # Check for vector index
    assert "vector_index_memories" in schema_content, "Vector index not found"
    assert "vector(f32, 768)" in schema_content, "Vector embedding dimension not found"
    
    # Check for search functions
    assert "ft_search_memories" in schema_content, "Full-text search function not found"
    assert "vector_search_memories" in schema_content, "Vector search function not found"
    assert "hybrid_search_memories" in schema_content, "Hybrid search function not found"
    
    # Check that filter parameters are properly named
    assert "filter_project_id" in schema_content, "Filter parameters not properly renamed"
    assert "filter_status" in schema_content, "Filter parameters not properly renamed"
    assert "filter_tags" in schema_content, "Filter parameters not properly renamed"
    
    print("✓ Cozo schema parsing test passed")


def test_cozo_schema_load():
    """Test that Cozo can load the schema (if cozo is available)."""
    try:
        import cozo
    except ImportError:
        pytest.skip("CozoDB package not installed")
    
    schema_path = Path(__file__).parent.parent / "cozodb" / "schema.cozo"
    
    # Create a temporary database
    with tempfile.NamedTemporaryFile(suffix=".cozo", delete=False) as tmp_db:
        db_path = tmp_db.name
    
    try:
        # Try to create a Cozo database with the schema
        db = cozo.CozoDb(db_path)
        
        # Read and execute the schema
        schema_content = schema_path.read_text()
        
        # Execute the schema (this will fail if there are syntax errors)
        db.execute(schema_content)
        
        print("✓ Cozo schema load test passed")
        
        # Clean up
        db.close()
        os.unlink(db_path)
        
    except Exception as e:
        # Clean up on error
        if os.path.exists(db_path):
            os.unlink(db_path)
        raise AssertionError(f"Failed to load Cozo schema: {e}")


if __name__ == "__main__":
    test_cozo_schema_parsing()
    test_cozo_schema_load()
    print("All Cozo schema tests passed!")
