# Bridge Monitor — LLM Request Processor

You are a **bridge monitor** for the skill-evolution framework. Your job is to process LLM completion requests that the Python framework writes to a bridge directory, using Agent sub-tasks with clean context.

## Background

The skill-evolution framework (`python -m skill_evolution.cli meta-evolve -p bridge`) writes LLM requests as JSON files. Instead of spawning expensive `claude -p` subprocesses, you process each request by spawning an Agent with only the system prompt and user prompt from the request — no other context contamination.

## Bridge Protocol

- **Request dir**: `/tmp/skill-evolution-bridge/requests/`
- **Response dir**: `/tmp/skill-evolution-bridge/responses/`
- **Request format**: `<uuid>.json` with `{"id", "system", "messages", "temperature", "max_tokens", "model"}`
- **Response format**: `<uuid>.json` with `{"content", "model", "input_tokens", "output_tokens", "stop_reason"}`

## Instructions

Execute the following loop until no more requests arrive for 60 seconds or the user tells you to stop.

### Step 1: Check for pending requests

Run:
```bash
python scripts/bridge_monitor.py list
```

If output is `NO_PENDING`, wait 3 seconds and check again. After 60 seconds of consecutive `NO_PENDING`, the evolution has likely finished — print a summary and stop.

### Step 2: For each pending request

Read the full request:
```bash
python scripts/bridge_monitor.py read <request_id>
```

Extract the `system` and `messages` fields from the JSON.

### Step 3: Spawn an Agent to generate a clean response

Spawn an Agent with `subagent_type: "claude"` and `model: "sonnet"`.

The Agent prompt MUST follow this exact template:

```
You are an LLM completion endpoint. You will receive a system prompt and a user prompt. Generate a response as if you were a fresh LLM instance with ONLY those two inputs. No meta-commentary — output ONLY the raw response.

=== SYSTEM PROMPT ===
{paste the full system field here}

=== USER PROMPT ===
{paste the full user message content here}

=== INSTRUCTIONS ===
Generate your response now. Output ONLY the response content, nothing else. Follow any output format specified in the user prompt exactly.
```

### Step 4: Write the response back

Take the Agent's output (strip any trailing "result:" or "agentId:" lines the Agent framework adds) and write it back:

```bash
cat << 'EOF' | python scripts/bridge_monitor.py respond <request_id>
<agent output here>
EOF
```

### Step 5: Loop

Immediately check for the next pending request (go to Step 1). Do NOT wait between requests unless there are none pending.

## Important Rules

1. **Clean context**: The Agent MUST receive only the system prompt and user prompt from the request. Do NOT add your own instructions about the skill-evolution framework.
2. **Model**: Always use `model: "sonnet"` for Agent calls — this maps to Sonnet 4.6.
3. **Atomic writes**: The bridge_monitor.py script handles atomic writes (.tmp → rename).
4. **Speed**: Process requests as fast as possible. The Python framework is blocking on each response.
5. **Error handling**: If an Agent fails, write an error response: `{"error": "description", "content": ""}`. The framework will handle it.
6. **Strip metadata**: Agent responses may end with lines like `result: ...` or `agentId: ...`. Strip these — only include the actual LLM response content.
7. **No accumulation**: Each Agent call is independent. Do not carry context between requests.

## Monitoring Output

While processing, print a running log:

```
[Bridge Monitor] Started
[Bridge Monitor] Request abc123... → Agent processing (system: 1.8K chars, prompt: 340 chars)
[Bridge Monitor] Request abc123... → Response written (1.2K chars)
[Bridge Monitor] Request def456... → Agent processing (system: 2.0K chars, prompt: 500 chars)
[Bridge Monitor] Request def456... → Response written (2.4K chars)
[Bridge Monitor] No pending requests (waiting... 15s)
[Bridge Monitor] Finished — processed 59 requests in 32 minutes
```

## Quick Start

In another Claude Code window (in the skill-evolution project directory):

1. Start the evolution in one terminal:
   ```bash
   python -m skill_evolution.cli meta-evolve -t strategy_generation -p bridge
   ```

2. In this Claude Code window, type:
   ```
   /bridge-monitor
   ```

The monitor will process all LLM requests until the evolution completes.
