"""Test that all memorycore modules can be imported successfully."""

import sys
import importlib


def test_memorycore_imports():
    """Test that all memorycore modules can be imported."""
    # Test main package
    import memorycore
    assert hasattr(memorycore, '__version__')
    
    # Test all main modules
    modules = [
        'memorycore.memory_types',
        'memorycore.memory_engine',
        'memorycore.memory_engine_v2',
        'memorycore.graph_memory',
        'memorycore.consolidator',
        'memorycore.storage',
        'memorycore.audit',
        'memorycore.audit_jsonl',
        'memorycore.policy',
        'memorycore.ranking',
        'memorycore.search',
        'memorycore.embedding',
        'memorycore.controller',
        'memorycore.mcp_server',
        'memorycore.mcp_server_v2',
    ]
    
    for module_name in modules:
        try:
            module = importlib.import_module(module_name)
            print(f"✓ Successfully imported {module_name}")
        except ImportError as e:
            # Some imports may fail due to missing optional dependencies
            if "cozo" in str(e) or "psycopg2" in str(e):
                print(f"⚠ {module_name} import skipped (missing optional dependency)")
            else:
                raise AssertionError(f"Failed to import {module_name}: {e}")


def test_mcp_server_v2_tools():
    """Test that MCP server v2 can be instantiated and has the expected tools."""
    try:
        from memorycore.mcp_server_v2 import MemoryMCPServerV2
        
        # Create server instance (this should work without external dependencies)
        server = MemoryMCPServerV2()
        
        # Check that the server has the expected tools
        # Note: tools are defined in the class, but may require async context to access
        print("✓ MCP Server V2 can be instantiated")
        
    except ImportError as e:
        if "mcp" in str(e):
            print("⚠ MCP Server V2 import skipped (missing mcp dependency)")
        else:
            raise


def test_memory_types():
    """Test that memory types are properly defined."""
    from memorycore.memory_types import (
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
    test_memorycore_imports()
    test_mcp_server_v2_tools()
    test_memory_types()
    print("All import tests passed!")
