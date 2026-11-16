# AI auto-replies

When enabled, an AI assistant answers visitor messages until a human takes over. Providers are called over plain HTTPS with the Python standard library, so there are no SDK dependencies.

## How it behaves

1. A visitor sends a message. After the database commit, the reply is generated **in the background**, so sending is never slowed down or broken by the provider.
2. The visitor sees a typing indicator. The answer then arrives as a message from `BOT_NAME`, marked with an *AI* badge.
3. The bot stops for good in that conversation when:
   - an operator sends a (non-internal) message, or
   - the visitor writes a `HANDOFF_KEYWORDS` word ("human", "operator", "اپراتور" …). The bot then posts `HANDOFF_REPLY` and operators get an `ai.handoff` notification, or
   - an operator switches **AI assistant** off in the details pane.
4. Bot messages never trigger the bot, so it cannot loop. Internal notes are never sent to the provider.
5. If the provider fails or times out, the error is logged without secrets and the visitor simply waits for a human.

## OpenAI / ChatGPT

```python
import os

SUPCHAT = {
    "AI": {
        "ENABLED": True,
        "PROVIDER": "openai",
        "API_KEY": os.environ["OPENAI_API_KEY"],
        "MODEL": "<model id, e.g. a current GPT model>",
        "SYSTEM_PROMPT": "You are Acme's support assistant. Answer briefly. Prices: ...",
    },
}
```

## Any OpenAI-compatible API

Set `BASE_URL` to the host's OpenAI-compatible root. supchat calls `{BASE_URL}/chat/completions`.

| Service | `BASE_URL` example |
|---|---|
| Groq | `https://api.groq.com/openai/v1` |
| OpenRouter | `https://openrouter.ai/api/v1` |
| Mistral | `https://api.mistral.ai/v1` |
| DeepSeek | `https://api.deepseek.com/v1` |
| Together | `https://api.together.xyz/v1` |
| Ollama (local) | `http://localhost:11434/v1` (no key needed) |
| LM Studio (local) | `http://localhost:1234/v1` |

Check each provider's documentation for current URLs and model names.

## Anthropic

```python
SUPCHAT = {
    "AI": {
        "ENABLED": True,
        "PROVIDER": "anthropic",
        "API_KEY": os.environ["ANTHROPIC_API_KEY"],
        "MODEL": "<an Anthropic model id>",
    },
}
```

This calls the Messages API (`POST https://api.anthropic.com/v1/messages` with the `x-api-key` and `anthropic-version` headers). `BASE_URL` can point at a gateway or proxy. A `refusal` stop reason is treated as "no answer", and a human takes over.

## Your own function

Use any SDK, a local model, retrieval over your docs, or rules:

```python
# myapp/bot.py
def reply(messages, conversation):
    """messages: [{"role": "user"|"assistant", "content": str}, ...] (oldest first)."""
    question = messages[-1]["content"]
    if "refund" in question.lower():
        return "Refunds take 3 business days. Anything else?"
    return ""  # empty string = stay silent and let a human answer

SUPCHAT = {"AI": {"ENABLED": True, "PROVIDER": "custom", "CALLABLE": "myapp.bot.reply"}}
```

## Model-specific options

- Some newer OpenAI models reject `max_tokens`. Set `"TOKEN_PARAM": "max_completion_tokens"`.
- Pass any extra request fields with `"EXTRA_BODY"`, for example `{"temperature": 0.3}`, or provider-specific reasoning or effort settings to make replies faster.
- Models that reason before answering spend part of `MAX_TOKENS` on that. If replies come back empty, raise `MAX_TOKENS` (default 1024) or lower the effort through `EXTRA_BODY`. An empty answer never reaches the visitor.

## Tips

- Put product facts, tone and limits in `SYSTEM_PROMPT`. Tell the model to offer a human when unsure.
- `MAX_HISTORY` controls how many recent messages are sent (default 20).
- The bot runs in a thread by default. If you already use Celery, you can disable `AI.ENABLED` and call `supchat.ai.maybe_auto_reply(conversation_id, message_id)` from your own task.
- Conversation content is sent to the provider you configure. Mention this in your privacy policy.
