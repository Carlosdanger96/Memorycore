# OpenAI Secure MCP Tunnel

This is the preferred ChatGPT web connection for a locally hosted Memorycore.
Memorycore, SQLite, the token registry, and the HTTP MCP server remain on the
Windows PC. `tunnel-client` makes an outbound HTTPS connection to OpenAI and
forwards approved ChatGPT MCP calls to `http://127.0.0.1:8000/mcp`. No inbound
port, public Memorycore URL, Cloudflare account, or cloud database is required.

## Connection boundary

```text
ChatGPT web → OpenAI tunnel endpoint → local tunnel-client
                                      → 127.0.0.1:8000/mcp
                                      → local Memorycore SQLite
```

The OpenAI runtime API key authenticates `tunnel-client` to OpenAI. The
`chatgpt-web` token from Memorycore's private registry separately authenticates
the tunnel client to Memorycore and fixes ChatGPT's local role/project scope.
Neither secret belongs in Git or in the generated YAML profile.

## One-time account setup

1. Open `https://platform.openai.com/settings/organization/tunnels`.
2. Create a tunnel associated with the personal Platform organization and the
   ChatGPT workspace that will use Memorycore. Copy the `tunnel_id`.
3. Ensure the operator has Tunnels Read + Use; creating the tunnel also needs
   Tunnels Read + Manage.
4. Create a separate runtime API key at
   `https://platform.openai.com/settings/organization/api-keys`.
5. Download the current Windows `tunnel-client` release from the tunnel page or
   `https://github.com/openai/tunnel-client/releases`. Put `tunnel-client.exe`
   in a directory on `PATH`.
6. In ChatGPT, enable developer mode under Settings → Security and login.

Use a runtime API key for the daemon. Do not use an OpenAI admin key, and do not
paste either the runtime key or the Memorycore token into chat.

## Start local Memorycore

In the Memorycore repository:

```powershell
.\.venv\Scripts\Activate.ps1
$env:MEMORYCORE_DB = "C:\Memorycore\data\memorycore.db"
$env:MEMORYCORE_HTTP_TOKENS_FILE = "C:\Memorycore\secrets\http-clients.production.json"
$env:MEMORYCORE_PUBLIC_URL = "http://127.0.0.1:8000/mcp"
memorycore serve-http --host 127.0.0.1 --port 8000
```

Keep this terminal running. Anonymous access should return `401`.

## Configure and run tunnel-client

Open a second PowerShell terminal in the repository and run the setup script
with the tunnel ID. If `CONTROL_PLANE_API_KEY` is not already set, the script
prompts for it without displaying it:

```powershell
.\scripts\setup-openai-tunnel.ps1 -TunnelId "tunnel_REPLACE_ME" -Run
```

The script:

- reads only the `chatgpt-web` token from the private production registry;
- writes a secret-free profile under `C:\Memorycore\secrets`;
- sends the bearer token to local Memorycore for runtime and discovery requests;
- confirms anonymous Memorycore access is rejected;
- runs `tunnel-client doctor --explain` before starting;
- exposes tunnel health/admin information only on `127.0.0.1:8080`.

Keep the tunnel terminal running. Check `http://127.0.0.1:8080/ui` and require
healthy/ready status before connecting ChatGPT.

## Connect ChatGPT

1. Open ChatGPT Settings → Plugins (developer mode).
2. Create a developer-mode app.
3. Under Connection, choose **Tunnel**.
4. Select the created tunnel or paste its `tunnel_id`.
5. Confirm Memorycore's tool list appears.
6. Start a new chat, enable the Memorycore app, call `memory_health`, retrieve
   project context, and create one pending test memory.

The `chatgpt-web` role is `writer`, so its new memory must remain pending until
a separate approver such as Mistral or Hermes approves it.

## Shutdown and rotation

Stop `tunnel-client` and Memorycore with `Ctrl+C`. Clear secret variables from
the terminal when finished:

```powershell
Remove-Item Env:CONTROL_PLANE_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:MEMORYCORE_TUNNEL_MCP_TOKEN -ErrorAction SilentlyContinue
```

If either token is exposed, revoke/rotate it before restarting. The OpenAI
tunnel solves ChatGPT reachability only; Mistral web still requires a connection
method supported by Mistral.
