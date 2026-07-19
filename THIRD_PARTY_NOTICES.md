# Third-Party Notices

Memorycore and Omni Memory Harness are distributed under the MIT License in
[`LICENSE`](LICENSE). The following components retain their respective terms.

| Component | Purpose | Required | License / terms |
| --- | --- | --- | --- |
| Python 3.11+ standard library | Storage, scanning, REST server, demo | Yes | Python Software Foundation License |
| MCP Python SDK | MCP server and protocol tests | Optional for base storage; required for MCP | MIT |
| pytest | Test execution | Development only | MIT |
| pytest-asyncio | Async MCP tests | Development only | Apache-2.0 |
| SQLAlchemy and psycopg | Optional PostgreSQL adapter | No | MIT / LGPL-3.0 |
| OpenAI Responses API | Live correction extraction and memory auditing | No | OpenAI API terms |

The default demonstration uses no external service. OpenAI calls require an
explicit environment flag and API credentials. No third-party source code is
copied into the repository.
