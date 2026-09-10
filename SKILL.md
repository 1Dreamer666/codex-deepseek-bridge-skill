---
name: codex-deepseek-subagent
description: Configure and maintain a native DeepSeek V4.1 Flash subagent for Codex through an OpenAI-compatible provider.
---

# Codex DeepSeek V4.1 Flash subagent

This skill configures and verifies native delegation to `deepseek-v4.1-flash`.

- Official model documentation: https://api-docs.deepseek.com/
- Official API endpoint: https://api.deepseek.com/chat/completions
- The model accepts text input. Keep API credentials in the operating system credential store.
- Verify native delegation by checking the child thread metadata and requiring the exact response token `NATIVE_DEEPSEEK_OK`.

License: GNU Affero General Public License v3.0.
