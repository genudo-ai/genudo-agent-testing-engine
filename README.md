# GenuDo Agent Testing Engine

Automated conversation testing for AI sales and support agents on the [GenuDo](https://genudo.ai) platform (WhatsApp, Messenger, Instagram and other channels).

Synthetic customers talk to your GenuDo agent through the GenuDo API, one message at a time, the same way a real customer would. Every AI reply is checked twice:

1. **Tier 1, deterministic checks:** per-step assertions (must contain, must not contain, regex, expected action fired, expected stage, reply language) and suite-wide guardrail rules.
2. **Tier 2, LLM judge (optional):** a semantic verdict against the suite's reference facts. It runs through your local AI subscription CLI (Claude Code or Codex). It never calls a paid API, and it never needs an API key.

The engine works for any business and any vertical. You describe the business, its facts and the journeys to test in a suite file (JSON or Excel).

> **Run against a staging or test pipeline first.**
> A run creates real opportunities (flagged `is_test`), sends real messages, and lets the agent fire its real actions. Those actions include webhooks into order sheets, CRMs and n8n/Zapier flows. Start with a duplicate or staging pipeline whose actions point at test destinations. Move to production only when you understand what a run triggers, and then pass `--allow-prod` explicitly.

---

## Requirements

- Python 3.9+. `openpyxl` is needed only for `.xlsx` suites and for `suite_builder.py`. JSON suites run on the standard library alone.
- **`GENUDO_TOKEN`**: a GenuDo API bearer token. The same token is used for both `{GENUDO_BASE}/mcp` (MCP tools: messages, action results, stages, bulk opportunity updates) and `{GENUDO_BASE}/api/user/*` (REST: create test opportunities, send test messages, pause conversations). Create it in the GenuDo console under **Developer → API Keys & Tokens → Create token**, with `mcp:use` plus the scopes that cover writing opportunities, conversations and messages (pick them by name from the console's scope list). The token is shown once; keep it in `.env`, never in the repo.
- **Inside a client folder?** If `GENUDO_TOKEN` is not set, the engine looks for the nearest `.mcp.json` at or above its own folder and reuses the `genudo` server's `Authorization: Bearer` token. Only an `https` `*.genudo.ai` server qualifies, only `${GENUDO_*}` references in it are expanded, and `GENUDO_BASE` is never taken from the file. Clone the engine inside a client folder made by `loredex workspace` and it needs no token of its own, as long as that token has the write scopes above.
- **An `Archived` stage in every pipeline you test.** At the end of a run, every test opportunity is moved to this stage and its conversation is paused, so test leads never stay in your live funnel. If the stage is missing, the engine warns you and leaves the opportunities where they are. The stage name can be changed with `GENUDO_ARCHIVED_STAGE`.
- Optional, for the LLM judge: the [`claude`](https://docs.anthropic.com/en/docs/claude-code) CLI (Claude Code subscription) or the [`codex`](https://github.com/openai/codex) CLI (ChatGPT subscription), logged in.

## Quickstart

```bash
git clone https://github.com/genudo-ai/genudo-agent-testing-engine.git
cd genudo-agent-testing-engine
python3 setup_env.py          # creates .venv, installs requirements, copies .env.example -> .env
# edit .env: GENUDO_TOKEN, GENUDO_PIPELINES (a staging pipeline!)
source .venv/bin/activate     # Windows: .venv\Scripts\activate

python3 src/engine.py list --suite templates/starter-suite.json
python3 src/engine.py run --pipeline messenger --dry-run
python3 src/engine.py run --pipeline messenger --cases J02 --run-no 1
```

## Configuration (environment or `.env`)

| Variable | Default | Purpose |
|---|---|---|
| `GENUDO_TOKEN` | required | Bearer token for `/mcp` and `/api/user/*` |
| `GENUDO_BASE` | `https://api.genudo.ai` | API base URL |
| `GENUDO_PIPELINES` | required | `channel=pipeline_id,...`, e.g. `messenger=12345,whatsapp=67890` |
| `GENUDO_ENV` | `dev` | Set to `prod` to make the engine refuse to run without `--allow-prod` |
| `GENUDO_ARCHIVED_STAGE` | `Archived` | Stage that test opportunities are moved to at the end of a run |
| `GENUDO_MCP_MAX_RPM` | `30` | MCP request budget. Calls are spaced at least 2.2s apart, and the engine backs off on rate-limit errors (`-32029` / HTTP 429) |
| `GENUDO_JUDGE` | auto | `claude`, `codex` or `off`. If unset, the engine uses `claude` if it is on PATH, then `codex`, and otherwise turns the judge off with a warning |
| `GENUDO_JUDGE_MODEL` | `haiku` (claude) | Optional model override passed to the judge CLI |

Real environment variables take precedence over `.env`. `.env` is gitignored.

## CLI

```text
python3 src/engine.py run      [--suite PATH] [--pipeline CHANNEL|all] [--run-no N]
                               [--cases J01,J02] [--priority P0|P0,P1|all] [--category TEXT]
                               [--workers N] [--stop-on-fail] [--keep-live]
                               [--allow-prod] [--dry-run]
python3 src/engine.py list     [--suite PATH]
python3 src/engine.py compare  OLD_RESULTS_JSON NEW_RESULTS_JSON
```

- `--suite`: a `.json` or `.xlsx` suite. Default: `templates/starter-suite.json`.
- `--pipeline`: a channel name from `GENUDO_PIPELINES`, or `all` for every configured channel. Default: `messenger`. A case runs on a channel only if its `pipelines` field is `all`, empty, or names that channel.
- `--run-no`: the `N` in the `TEST R<N>` labels and the run id. Default: derived from the clock.
- `--cases`, `--priority`, `--category`: filters. `--category` matches a case-insensitive substring.
- `--workers`: the number of cases that run concurrently. Default: 3. MCP calls are throttled globally whatever this is set to.
- `--stop-on-fail`: stops a case at its first failing step.
- `--keep-live`: skips cleanup, so test opportunities are not archived and their conversations are not paused.
- `--allow-prod`: required when `GENUDO_ENV=prod`.
- `--dry-run`: prints the selected journeys and exits. It makes no network calls and writes no files.
- `compare`: lists regressions (pass → not pass) and fixes between two runs. It exits with `1` if there is any regression.

Exit code of `run`: `1` if any **P0** case did not pass, otherwise `0`.

## Test isolation and safety

Every case:

- creates its own opportunity with `is_test: true`, tags `autotest` + the run id, and a note saying it is safe to delete;
- uses a unique `…@example.com` contact email and a contact name suffixed `- TEST R<N>`;
- appends `- TEST R<N>` to any name the synthetic customer types, so orders and tickets the agent creates in downstream sheets and CRMs are easy to find and delete;
- waits for the agent to finish answering before it checks anything. It polls every 3.5s and treats 14s of silence as "done", with a 150s maximum per message;
- attributes each fired action to the first step that sees it, so a late webhook is never counted twice.

At the end of a run, cleanup moves every test opportunity to the `Archived` stage and pauses its conversation. Cleanup runs in a `finally` block, so it also happens when a run crashes or is interrupted.

## Suite format

A suite has four parts. In JSON they are top-level keys. In Excel each one is a tab (Cases and Steps are separate tabs).

- **cases / Cases + Steps**: journeys of 4–15 steps. Each case has `case_id`, `short_name`, `contact_name`, `category`, `priority` (P0/P1/P2), `pipelines`, an optional `start_stage` and a `description`. Each step has `customer_message`, an optional `image` (a file in `templates/fixtures/`), `expected_reply` and assertions:
  - `must_contain_all`, `must_contain_any`, `must_not_contain`: `||`-separated. Matching ignores case, Arabic diacritics and alef/yaa variants, and treats Arabic-Indic and Latin digits as the same.
  - `regex_must`, `regex_forbidden`
  - `expect_action`: an action-name prefix, or `none` to mean no action may fire. `expect_payload_contains` checks the fired action's payload.
  - `expect_stage`, `expect_stage_not`
  - `language`: `ar` or `en`. If omitted, the language is detected from the customer's message.
  - `judge_rubric`: the instruction for the LLM judge.
  - `severity`: `critical`, `major` or `minor`. A failed check on a `critical` or `major` step fails the step. On a `minor` step it only produces a warning.
- **global_rules / GlobalRules**: guardrails checked on every reply. Types: `regex_forbidden`, `links_allowlist`, `max_emoji`, `min_length`, `no_duplicates`, `action_payload_forbidden`. A rule's `exempt_if_reply_contains` (`||`-separated) skips the rule for any reply that contains one of those texts.
- **facts / Facts**: the business ground truth (prices, policies, payment details). The LLM judge grades replies against it.
- **brand_terms / BrandTerms**: brand, product, currency and payment-provider names that are written the same in every language. They are removed before language detection, so an Arabic reply that names a Latin-script product still counts as Arabic.

`templates/starter-suite.json` is a vertical-neutral example: a fictional "Demo Store" with an Arabic order journey, English policy questions, and an edge-case journey that uses an image. Replace its facts, rules and journeys with your own.

```bash
python3 src/suite_builder.py --input templates/starter-suite.json --validate                # validate only
python3 src/suite_builder.py --input my-suite.json --output-xlsx my-suite.xlsx            # validate + build Excel
```

## LLM judge

The judge sends the conversation so far, the reply, the expected behaviour, the rubric and the suite facts to:

- `claude -p --model haiku` (Claude Code subscription). This is the default when it is installed.
- `codex exec --sandbox read-only -` (ChatGPT subscription through the Codex CLI).

The prompt goes in on stdin. The first JSON object in the output that contains a verdict, `{"verdict": "pass"|"fail", "reason": "..."}`, is used. A `fail` fails the step, unless the step is `minor`, in which case it only produces a warning. If the CLI is missing, times out (120s), or returns no verdict, the step records `judge_error` and keeps its Tier-1 verdict. Set `GENUDO_JUDGE=off` to run deterministic checks only.

Agent replies are untrusted input to the judge, so the judge CLI runs with no tools (`claude --tools "" --strict-mcp-config`; `codex` in its read-only sandbox, `--ephemeral`), in an empty temporary directory, without any `GENUDO_*` variables, and without `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`, so it always bills your subscription login, never an API key. A token that still shows up in a verdict reason is redacted.

## Outputs

Each non-dry run writes `runs/<run-id>/` (gitignored):

- `results.json`: the full machine-readable result, including every reply, check, fired action, stage and judge verdict.
- `report.html`: a self-contained report.

Run output contains full conversation transcripts. Treat it as sensitive.

## CI

`.github/workflows/agent-tests.yml` runs the engine's own self-check, then a live run on manual dispatch. Set the `GENUDO_TOKEN` secret, plus the `GENUDO_PIPELINES` and optional `GENUDO_BASE` repository variables, and point them at a staging pipeline. A CI runner has no AI subscription CLI, so CI runs with `GENUDO_JUDGE=off` (deterministic checks only). Artifacts are kept for 7 days. On a public repository, anyone with read access can download them.

## Engine self-check

```bash
python3 tests/test_judge.py && python3 tests/test_config.py   # or: python3 -m pytest tests/
```

## License

MIT. See [LICENSE](LICENSE).
