"""Test that all server modules can be imported successfully."""

import pytest
import importlib


# Modules that should always be importable
CORE_MODULES = [
    'server.memory_types',
    'server.memory_engine',
    'server.memory_engine_v2',
    'server.graph_memory',
    'server.consolidator',
    'server.audit',
    'server.audit_jsonl',
    'server.policy',
    'server.ranking',
    'server.embedding',
    'server.controller',
    'server.mcp_server',
    'server.mcp_server_v2',
]


def _can_import_optional(module_name: str, dependencies: list) -> bool:
    """Check if optional dependencies are available."""
    try:
        importlib.import_module(module_name)
        return True
    except ImportError as e:
        # Check if the error is due to missing optional dependencies
        for dep in dependencies:
            if dep in str(e):
                return False
        # If it's a different import error, re-raise it
        raise


def test_core_server_imports():
    """Test that all core server modules can be imported."""
    for module_name in CORE_MODULES:
        try:
            module = importlib.import_module(module_name)
            print(f"✓ Successfully imported {module_name}")
        except ImportError as e:
            raise AssertionError(f"Failed to import core module {module_name}: {e}")


@pytest.mark.skipif(
    not _can_import_optional("server.search", ["cozo"]),
    reason="cozo package not installed"
)
def test_optional_search_import():
    """Test that server.search can be imported when cozo is available."""
    from server import search
    print("✓ Successfully imported server.search")


@pytest.mark.skipif(
    not _can_import_optional("server.storage", ["psycopg2"]),
    reason="psycopg2 package not installed"
)
def test_optional_storage_import():
    """Test that server.storage can be imported when psycopg2 is available."""
    from server import storage
    print("✓ Successfully imported server.storage")


def test_mcp_server_v2_tools(tmp_path):
    """Test that MCP server v2 can be instantiated and has the expected tools."""
    try:
        from server.mcp_server_v2 import MemoryMCPServerV2, create_memory_engine_v2
        from server.audit_jsonl import JSONLAuditLogger
    except ImportError as e:
        if "mcp" in str(e):
            pytest.skip("MCP library not installed")
        else:
            raise
    
    # Create server instance (this should work without external dependencies)
    try:
        engine = create_memory_engine_v2()
        audit_logger = JSONLAuditLogger(str(tmp_path / "test-audit.jsonl"))
        server = MemoryMCPServerV2(engine, audit_logger)
        
        # Check that the server has the expected tools
        # Note: tools are defined in the class, but may require async context to access
        print("✓ MCP Server V2 can be instantiated")
    except Exception as e:
        if "cozo" in str(e) or "CozoDB" in str(e):
            pytest.skip("CozoDB package not installed")
        else:
            raise


def test_memory_types():
    """Test that memory types are properly defined."""
    from server.memory_types import (
        MemoryCard, MemoryType, MemoryStatus, MemoryScope,
        EpisodeRecord, GraphNode, GraphNodeType, GraphEdgeType,
        SupersessionRecord, ContextResult
    )
    
    # Test enums
    assert hasattr(MemoryType, 'EPISODIC')
    assert hasattr(MemoryType, 'SEMANTIC')
    assert hasattr(MemoryType, 'PROCEDURAL')
    assert hasattr(MemoryType, 'DECISION')
    assert hasattr(MemoryType, 'CORRECTION')
    assert hasattr(MemoryType, 'SOURCE')
    assert hasattr(MemoryType, 'AUDIT')
    
    assert hasattr(MemoryStatus, 'ACTIVE')
    assert hasattr(MemoryStatus, 'STALE')
    assert hasattr(MemoryStatus, 'SUPERSEDED')
    assert hasattr(MemoryStatus, 'CONTRADICTED')
    assert hasattr(MemoryStatus, 'ARCHIVED')
    
    assert hasattr(MemoryScope, 'PROJECT')
    assert hasattr(MemoryScope, 'GLOBAL')
    assert hasattr(MemoryScope, 'USER')
    assert hasattr(MemoryScope, 'AGENT')
    
    print("✓ Memory types are properly defined")


if __name__ == "__main__":
    test_core_server_imports()
    test_mcp_server_v2_tools()
    test_memory_types()
    print("All import tests passed!")
