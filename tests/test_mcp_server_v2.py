"""MCP Server v2 smoke tests."""

import asyncio
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional


def test_mcp_server_v2_tool_list():
    """Test that MCP Server v2 defines the expected tools."""
    try:
        from memorycore.mcp_server_v2 import MemoryMCPServerV2
    except ImportError as e:
        if "mcp" in str(e):
            print("⚠ MCP library not available, skipping MCP server tests")
            return
        else:
            raise
    
    # Create server instance
    server = MemoryMCPServerV2()
    
    # Check that the server has the expected tools
    # The tools are defined in the get_tools method
    tools = server.get_tools()
    
    # Expected tool names
    expected_tools = [
        # Memory operations
        "memory.record_episode",
        "memory.add_card", 
        "memory.retrieve_context",
        "memory.supersede",
        "memory.audit",
        "memory.search",
        "memory.consolidate_episode",
        "memory.consolidate_project",
        
        # Graph operations
        "graph.add_node",
        "graph.add_edge",
        "graph.traverse",
        "graph.get_summary",
        
        # System operations
        "system.health_check",
        "system.get_config",
    ]
    
    # Check that all expected tools are present
    tool_names = [tool.name for tool in tools]
    
    for expected_tool in expected_tools:
        assert expected_tool in tool_names, f"Expected tool {expected_tool} not found in tool list"
        print(f"✓ Found tool: {expected_tool}")
    
    # Check that we have exactly 14 tools
    assert len(tool_names) == 14, f"Expected 14 tools, found {len(tool_names)}"
    
    print(f"✓ MCP Server v2 has all {len(tool_names)} expected tools")


def test_mcp_server_v2_tool_schemas():
    """Test that MCP Server v2 tools have proper schemas."""
    try:
        from memorycore.mcp_server_v2 import MemoryMCPServerV2
    except ImportError as e:
        if "mcp" in str(e):
            print("⚠ MCP library not available, skipping MCP server schema tests")
            return
        else:
            raise
    
    server = MemoryMCPServerV2()
    tools = server.get_tools()
    
    for tool in tools:
        # Check that each tool has required fields
        assert hasattr(tool, 'name'), f"Tool missing 'name' field"
        assert hasattr(tool, 'description'), f"Tool {tool.name} missing 'description' field"
        assert hasattr(tool, 'inputSchema'), f"Tool {tool.name} missing 'inputSchema' field"
        
        # Check that input schema is a dict
        assert isinstance(tool.inputSchema, dict), f"Tool {tool.name} has invalid inputSchema"
        
        # Check for common schema properties
        schema = tool.inputSchema
        assert 'type' in schema, f"Tool {tool.name} schema missing 'type'"
        assert schema['type'] == 'object', f"Tool {tool.name} schema type should be 'object'"
        
        print(f"✓ Tool {tool.name} has valid schema")


def test_mcp_server_v2_initialization():
    """Test that MCP Server v2 can be initialized with different configurations."""
    try:
        from memorycore.mcp_server_v2 import MemoryMCPServerV2, create_memory_engine_v2
    except ImportError as e:
        if "mcp" in str(e):
            print("⚠ MCP library not available, skipping MCP server initialization tests")
            return
        else:
            raise
    
    # Test with default configuration
    server1 = MemoryMCPServerV2()
    assert server1 is not None
    print("✓ MCP Server v2 initialized with default config")
    
    # Test with custom engine
    engine = create_memory_engine_v2()
    server2 = MemoryMCPServerV2(memory_engine=engine)
    assert server2 is not None
    print("✓ MCP Server v2 initialized with custom engine")
    
    # Test with disabled features
    server3 = MemoryMCPServerV2(
        use_graph_memory=False,
        use_consolidation=False,
        auto_consolidate=False
    )
    assert server3 is not None
    print("✓ MCP Server v2 initialized with disabled features")


def test_memory_types_in_mcp_server():
    """Test that memory types used in MCP server are properly defined."""
    try:
        from memorycore.mcp_server_v2 import MemoryMCPServerV2
        from memorycore.memory_types import (
            MemoryCard, MemoryType, MemoryStatus, MemoryScope,
            EpisodeRecord, GraphNode, GraphNodeType, GraphEdgeType,
            SupersessionRecord, ContextResult
        )
    except ImportError as e:
        if "mcp" in str(e):
            print("⚠ MCP library not available, skipping memory types tests")
            return
        else:
            raise
    
    # Test that all expected memory types are available
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
    
    print("✓ All memory types are properly defined and accessible")


def test_tool_list_snapshot():
    """Test that the tool list matches the expected snapshot."""
    try:
        from memorycore.mcp_server_v2 import MemoryMCPServerV2
    except ImportError as e:
        if "mcp" in str(e):
            print("⚠ MCP library not available, skipping tool list snapshot test")
            return
        else:
            raise
    
    server = MemoryMCPServerV2()
    tools = server.get_tools()
    
    # Create a snapshot of the current tool list
    tool_snapshot = {
        'count': len(tools),
        'names': sorted([tool.name for tool in tools]),
        'categories': {}
    }
    
    # Categorize tools
    for tool in tools:
        name = tool.name
        if name.startswith('memory.'):
            tool_snapshot['categories']['memory'] = tool_snapshot['categories'].get('memory', 0) + 1
        elif name.startswith('graph.'):
            tool_snapshot['categories']['graph'] = tool_snapshot['categories'].get('graph', 0) + 1
        elif name.startswith('system.'):
            tool_snapshot['categories']['system'] = tool_snapshot['categories'].get('system', 0) + 1
    
    # Verify expected categories
    assert tool_snapshot['categories'].get('memory', 0) == 8, f"Expected 8 memory tools, got {tool_snapshot['categories'].get('memory', 0)}"
    assert tool_snapshot['categories'].get('graph', 0) == 4, f"Expected 4 graph tools, got {tool_snapshot['categories'].get('graph', 0)}"
    assert tool_snapshot['categories'].get('system', 0) == 2, f"Expected 2 system tools, got {tool_snapshot['categories'].get('system', 0)}"
    
    print(f"✓ Tool list snapshot: {tool_snapshot['count']} tools in categories: {tool_snapshot['categories']}")


if __name__ == "__main__":
    test_mcp_server_v2_tool_list()
    test_mcp_server_v2_tool_schemas()
    test_mcp_server_v2_initialization()
    test_memory_types_in_mcp_server()
    test_tool_list_snapshot()
    print("All MCP v2 smoke tests passed!")
