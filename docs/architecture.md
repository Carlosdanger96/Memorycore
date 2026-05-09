# Architecture

`memory.exe-core` is an infrastructure project for shared LLM memory over MCP.

## System flow
MCP Gateway → Policy Layer → Memory Engine → Storage → Workers

## MVP boundaries
The MVP intentionally excludes advanced features (graph memory, glyph compression, distributed agents, and full Obsidian automation) to keep the first release auditable and maintainable.
