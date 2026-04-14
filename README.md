# Hermes Agent + Home Assistant Assist

This directory contains a Home Assistant custom component that lets Assist use Hermes Agent through Hermes's OpenAI-compatible API server.

What it does
- registers a Home Assistant conversation agent named `Hermes Agent Conversation`
- optionally tries Home Assistant local intent handling first
- falls back to Hermes over `POST /v1/chat/completions`
- uses `stream=true` for low-latency Assist responses
- preserves multi-turn context via `X-Hermes-Session-Id`
- strips markdown and hidden reasoning tags before TTS speaks the answer

Directory layout
- `custom_components/hermes_agent_conversation/` — copy this folder into Home Assistant

Prerequisites on the Hermes side
1. Enable the API server.
2. Set an API key. This is strongly recommended and effectively required if you want session continuity.

Example environment:

```bash
API_SERVER_ENABLED=true
API_SERVER_HOST=0.0.0.0
API_SERVER_PORT=8642
API_SERVER_KEY=change-me
```

Then start the gateway:

```bash
hermes gateway
```

Quick local test:

```bash
curl http://127.0.0.1:8642/health
curl http://127.0.0.1:8642/v1/models -H "Authorization: Bearer change-me"
```

Install into Home Assistant

Copy the custom component directory into Home Assistant:

```bash
scp -P 22222 -r \
  integrations/homeassistant/custom_components/hermes_agent_conversation \
  root@192.168.25.5:/config/custom_components/
```

Or, using the verified SSH target from this environment:

```bash
./integrations/homeassistant/deploy_to_user_ha.sh
```

Equivalent manual commands:

```bash
HA_SSH="ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=8 -p 22222 root@192.168.25.5"
scp -P 22222 -r integrations/homeassistant/custom_components/hermes_agent_conversation root@192.168.25.5:/config/custom_components/
$HA_SSH 'ha core check'
$HA_SSH 'ha core restart'
```

Configure in Home Assistant
1. Go to Settings -> Devices & Services -> Add Integration.
2. Search for `Hermes Agent Conversation`.
3. Enter:
   - Hermes API server URL, for example `http://192.168.25.167:8642/v1`
   - API key from `API_SERVER_KEY`
   - model name, usually `hermes-agent` or your Hermes profile name
4. In the options flow, tune:
   - additional system prompt
   - local-first behavior
   - session continuity
   - request timeout

Use with Assist
- Create or edit an Assist pipeline and choose `Hermes Agent Conversation` as the conversation engine.
- Keep STT/TTS in Home Assistant or Nabu Casa as usual.
- If `Prefer local Home Assistant handling first` is enabled, Home Assistant gets first crack at strict/local intents before Hermes is called.

Important notes
- Session continuity relies on `X-Hermes-Session-Id`, and Hermes only accepts that header when `API_SERVER_KEY` is configured.
- Hermes streams custom `hermes.tool.progress` SSE events; this component ignores them so TTS only speaks natural text.
- If your Hermes model name differs from `hermes-agent`, set the correct value in the integration config.
- If local-first behavior causes undesirable routing, disable `prefer_local` in the options flow.

Suggested deployment workflow for this user's HA host

```bash
HA_SSH="ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=8 -p 22222 root@192.168.25.5"
$HA_SSH 'git -C /config status --short --branch'
$HA_SSH 'ts=$(date +%Y%m%d-%H%M%S); cp -r /config/custom_components/hermes_agent_conversation /config/custom_components/hermes_agent_conversation.bak.$ts 2>/dev/null || true'
scp -P 22222 -r integrations/homeassistant/custom_components/hermes_agent_conversation root@192.168.25.5:/config/custom_components/
$HA_SSH 'ha core check && ha core restart'
```

Troubleshooting
- 401 or 403 from Hermes: verify `API_SERVER_KEY` and the configured URL.
- No multi-turn continuity: ensure the API key is configured on Hermes and session continuity is enabled in the integration options.
- Slow response or timeout: increase the request timeout option and verify the Hermes gateway is reachable from the HA host.
- Wrong model name: call `/v1/models` on Hermes and match the configured model exactly.
