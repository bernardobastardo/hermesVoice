---
title: Home Assistant Assist
sidebar_label: Home Assistant Assist
sidebar_position: 6
description: Use Hermes Agent as a Home Assistant Assist conversation engine through a custom component.
---

# Home Assistant Assist + Hermes Agent

Hermes can already talk to Home Assistant through the Home Assistant toolset and gateway adapter. This integration does the opposite direction: it lets Home Assistant Assist use Hermes as the conversation engine.

Architecture:

- Assist captures speech and handles wake word, STT, and TTS as usual.
- A Home Assistant custom component forwards conversation turns to Hermes.
- The component can try Home Assistant local intents first.
- If local handling does not resolve the request, it falls back to Hermes through Hermes's OpenAI-compatible API server.

## Why use this

Use this when you want:
- a voice pipeline built around Home Assistant Assist
- Hermes tools, memory, and skills behind that voice pipeline
- Home Assistant STT/TTS with Hermes reasoning and tool use
- local intents for simple commands and Hermes for everything else

## Requirements

On the Hermes host:

```bash
API_SERVER_ENABLED=true
API_SERVER_HOST=0.0.0.0
API_SERVER_PORT=8642
API_SERVER_KEY=change-me
```

Then start Hermes:

```bash
hermes gateway
```

The API key is strongly recommended and effectively required if you want session continuity via `X-Hermes-Session-Id`.

## Custom component location

Hermes ships the Home Assistant custom component in this repo at:

```text
integrations/homeassistant/custom_components/hermes_agent_conversation/
```

Copy that directory into your Home Assistant instance under:

```text
/config/custom_components/hermes_agent_conversation/
```

## Example deployment for the user's verified HA host

This environment already has working SSH access to Home Assistant at `root@192.168.25.5:22222`.

```bash
HA_SSH="ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=8 -p 22222 root@192.168.25.5"
$HA_SSH 'git -C /config status --short --branch'
scp -P 22222 -r integrations/homeassistant/custom_components/hermes_agent_conversation root@192.168.25.5:/config/custom_components/
$HA_SSH 'ha core check && ha core restart'
```

## Configure the integration in Home Assistant

1. Open Settings -> Devices & Services.
2. Add `Hermes Agent Conversation`.
3. Enter:
   - Hermes API Server URL, for example `http://192.168.25.167:8642/v1`
   - API key from `API_SERVER_KEY`
   - model name, usually `hermes-agent` or your profile name
4. In options, tune:
   - additional system prompt
   - prefer local handling first
   - session continuity
   - request timeout

## Use it in an Assist pipeline

Create or edit an Assist pipeline and set the conversation engine to `Hermes Agent Conversation`.

A good pattern is:
- wake word: Home Assistant or hardware device
- STT: Home Assistant Cloud, OpenAI, Whisper, or your usual choice
- conversation engine: Hermes Agent Conversation
- TTS: Home Assistant Cloud or your preferred engine

## How fallback works

When `prefer_local` is enabled:

1. Home Assistant local intent handling runs first.
2. If Home Assistant resolves the turn locally, that answer is used.
3. If Home Assistant returns a no-match or error-like result, the custom component calls Hermes.

When `prefer_local` is disabled:
- every turn goes straight to Hermes.

## Hermes API details used by the component

The custom component calls:

- `POST /v1/chat/completions`
- with `stream=true`
- and sends `X-Hermes-Session-Id` when session continuity is enabled

The component only speaks the assistant text stream. Hermes emits custom `hermes.tool.progress` SSE events for frontend UX, and the component ignores those so TTS stays clean.

## Speech-friendly behavior

The component sanitizes output before TTS:
- strips markdown formatting
- strips tags like `<think>` and `<final>`
- collapses noisy spacing

It also prepends a default speech-oriented system prompt so Hermes answers briefly and naturally for spoken output.

## Troubleshooting

### Home Assistant says it cannot connect
- verify the Hermes gateway is running
- verify the URL reaches Hermes from the HA host
- verify the bearer token matches `API_SERVER_KEY`

### Session continuity does not work
- make sure `API_SERVER_KEY` is configured on Hermes
- enable session continuity in the Home Assistant integration options

### Responses are too slow
- increase the request timeout in the integration options
- verify the Hermes model is responsive enough for voice use
- test Hermes directly with curl against `/v1/chat/completions`

### The wrong model is used
- call `GET /v1/models` on Hermes and use the exact returned model name
- if you run Hermes with profiles, the exposed model name may be the profile name rather than `hermes-agent`

### Local-first behavior feels wrong
- disable `prefer_local`
- or improve local HA intents, aliases, areas, and `custom_sentences`

## Related docs

- [API Server](/docs/user-guide/features/api-server)
- [Home Assistant](/docs/user-guide/messaging/homeassistant)
