"""
Evaluation and Judgment Engine:
Tier 1 - deterministic checks (per-step assertions + suite GlobalRules).
Tier 2 - LLM-as-a-judge semantic evaluation against the suite's reference facts.

The LLM judge runs ONLY through a locally installed AI subscription CLI - never a paid API,
and no API keys are read anywhere:
  * claude  -> `claude -p --model haiku`   (Claude Code subscription)  [default]
  * codex   -> `codex exec`                (ChatGPT subscription via Codex CLI)
  * off     -> deterministic tier only
Select with GENUDO_JUDGE=claude|codex|off. If unset, auto-detects `claude`, then `codex`, else off.
"""

import os
import re
import sys
import json
import shutil
import difflib
import subprocess
import tempfile

_AR_DIG = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

def norm(s):
    if not s:
        return ""
    s = s.translate(_AR_DIG)
    s = re.sub(r"[\u064b-\u065f\u0670\u0640]", "", s)
    s = re.sub(r"[إأآا]", "ا", s)
    s = re.sub(r"[يى]", "ي", s)
    s = re.sub(r"ة", "ه", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()

def parts(s):
    return [p.strip() for p in (s or "").split("||") if p.strip()]

EMOJI = re.compile(r"[\U0001F300-\U0001FAFF☀-➿⭐❤✅✨]")
URL = re.compile(r"https?://[^\s)»\]]+")

def brand_regex(brand_terms):
    """Compile the suite's `brand_terms` (brand / product / payment-provider names that are written
    the same in every language) into one regex. They are removed before language detection so an
    Arabic reply that names an English-spelled product is not counted as English (and vice versa)."""
    terms = [t.strip() for t in (brand_terms or []) if t and t.strip()]
    if not terms:
        return None
    terms.sort(key=len, reverse=True)
    return re.compile("|".join(re.escape(t) for t in terms), re.I)

def strip_brands(text, brand_terms=None):
    rx = brand_regex(brand_terms)
    return rx.sub("", text or "") if rx else (text or "")

def user_lang(text, brand_terms=None):
    t = strip_brands(URL.sub("", re.sub(r"\S+@\S+", "", text or "")), brand_terms)
    if re.search(r"[\u0600-\u06ff]", t):
        return "ar"
    words = re.findall(r"[A-Za-z0-9]*[A-Za-z][A-Za-z0-9]*", t)
    if len(words) < 2:
        return None
    if any(re.search(r"[A-Za-z]\d|\d[A-Za-z]", w) for w in words):
        return "ar"
    return "en"

def arabic_ratio(s, brand_terms=None):
    s = URL.sub("", strip_brands(s, brand_terms))
    ar = len(re.findall(r"[\u0600-\u06ff]", s))
    la = len(re.findall(r"[A-Za-z]", s))
    return ar / (ar + la) if ar + la else None

def run_checks(step, replies, user_text, rules, actions, stage_name, conv_lang=None, brand_terms=None):
    """Tier-1 checks. Returns a list of {name, ok, severity, detail}.
    `brand_terms` comes from the suite (top-level "brand_terms" list / BrandTerms sheet)."""
    res = []
    full = "\n".join(replies)
    nfull = norm(full)

    def add(name, ok, sev, detail=""):
        res.append({"name": name, "ok": bool(ok), "severity": sev, "detail": detail})

    sev = (step.get("severity") or "major").lower()
    if not replies:
        add("reply received", False, "critical", "no AI reply within timeout")
        return res

    add("reply received", True, "critical")

    for p in parts(step.get("must_contain_all")):
        add(f"contains '{p}'", norm(p) in nfull, sev)

    anys = parts(step.get("must_contain_any"))
    if anys:
        add("contains any of: " + " | ".join(anys), any(norm(p) in nfull for p in anys), sev)

    for p in parts(step.get("must_not_contain")):
        add(f"does not contain '{p}'", norm(p) not in nfull, sev)

    if step.get("regex_must"):
        add(f"matches /{step['regex_must']}/", re.search(norm(step["regex_must"]), nfull) is not None, sev)

    if step.get("regex_forbidden"):
        m = re.search(norm(step["regex_forbidden"]), nfull)
        add(f"must not match /{step['regex_forbidden']}/", m is None, sev, m.group(0) if m else "")

    # Actions and stage
    exp = (step.get("expect_action") or "").strip().lower()
    fired = [a["action_name"].lower() for a in actions]
    if exp:
        if exp == "none":
            add("no action fired", not fired, "critical", ", ".join(fired))
        else:
            add(f"action '{exp}' fired", any(a.startswith(exp) for a in fired), "critical", "fired: " + (", ".join(fired) or "none"))

    want_payload = parts(step.get("expect_payload_contains"))
    if want_payload:
        blob = json.dumps([a.get("payload") for a in actions], ensure_ascii=False)
        for p in want_payload:
            add(f"action payload contains '{p}'", p in blob, "critical", blob[:200])

    if step.get("expect_stage"):
        add(f"stage is '{step['expect_stage']}'", norm(stage_name or "") == norm(step["expect_stage"]), "critical", f"stage: {stage_name}")

    if step.get("expect_stage_not"):
        add(f"stage is not '{step['expect_stage_not']}'", norm(stage_name or "") not in [norm(x) for x in parts(step["expect_stage_not"])], "critical", f"stage: {stage_name}")

    # Language ratio
    want = (step.get("language") or "").lower()
    ratio = arabic_ratio(full, brand_terms)
    lang = want or user_lang(user_text, brand_terms) or conv_lang
    if lang and ratio is not None:
        add(f"language is {lang}", ratio >= 0.6 if lang == "ar" else ratio <= 0.25, "major", f"arabic ratio {ratio:.2f}")

    # Suite-level global guardrail rules (GlobalRules)
    for r in rules:
        typ, pat = r["type"], r["pattern"]
        if typ == "language_match":
            continue
        exempt = parts(r.get("exempt_if_reply_contains"))
        if typ == "action_payload_forbidden":
            blob = json.dumps([a.get("payload") for a in actions], ensure_ascii=False)
            m = re.search(pat, blob)
            add(f"[{r['rule_id']}] {r['description']}", m is None, r["severity"], m.group(0) if m else "")
            continue
        for rep in replies:
            if typ == "max_emoji":
                txt = rep
                for x in exempt:
                    txt = txt.replace(x, "")
                n = len(EMOJI.findall(txt))
                add(f"[{r['rule_id']}] {r['description']}", n <= int(pat), r["severity"], f"{n} emoji")
                continue
            if any(norm(x) in norm(rep) for x in exempt):
                continue
            if typ == "regex_forbidden":
                m = re.search(norm(pat), norm(rep))
                add(f"[{r['rule_id']}] {r['description']}", m is None, r["severity"], m.group(0) if m else "")
            elif typ == "links_allowlist":
                bad = [u for u in URL.findall(rep) if not any(u.startswith(ok) for ok in parts(pat.replace("|", "||")))]
                add(f"[{r['rule_id']}] {r['description']}", not bad, r["severity"], ", ".join(bad))
            elif typ == "min_length":
                add(f"[{r['rule_id']}] {r['description']}", len(rep.strip()) >= int(pat), r["severity"])

        if typ == "no_duplicates" and len(replies) > 1:
            worst = max((difflib.SequenceMatcher(None, a, b).ratio() for i, a in enumerate(replies) for b in replies[i + 1:]), default=0)
            add(f"[{r['rule_id']}] {r['description']}", worst < float(pat), r["severity"], f"similarity {worst:.2f}")

    return res

JUDGE_TIMEOUT = 120

def resolve_judge_backend():
    """GENUDO_JUDGE=claude|codex|off; unset/auto -> first CLI found on PATH (claude, then codex), else off."""
    want = (os.environ.get("GENUDO_JUDGE") or "auto").strip().lower()
    if want in ("off", "none", "0", "false"):
        return "off"
    if want in ("claude", "codex"):
        if not shutil.which(want):
            print(f"WARNING: GENUDO_JUDGE={want} but `{want}` is not on PATH - LLM judge disabled, deterministic checks only.", file=sys.stderr)
            return "off"
        return want
    for cli in ("claude", "codex"):
        if shutil.which(cli):
            return cli
    print("WARNING: no `claude` or `codex` CLI found on PATH - LLM judge disabled, deterministic checks only. "
          "Install one (or set GENUDO_JUDGE=off to silence this).", file=sys.stderr)
    return "off"

def _judge_cmd(backend):
    model = os.environ.get("GENUDO_JUDGE_MODEL", "").strip()
    # The prompt carries untrusted agent replies, so the judge gets no tools, no MCP servers,
    # no GENUDO_* env and an empty working dir (see _judge_env / call site).
    if backend == "claude":
        return ["claude", "-p", "--model", model or "haiku", "--tools", "", "--strict-mcp-config"]
    # ponytail: codex can't disable its shell; read-only sandbox + empty cwd + scrubbed env limit it
    cmd = ["codex", "exec", "--skip-git-repo-check", "--sandbox", "read-only", "--ephemeral"]
    if model:
        cmd += ["-m", model]
    return cmd + ["-"]

# API keys are dropped so the CLIs fall back to the user's subscription login, never paid API billing.
_JUDGE_ENV_DROP = {"ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "CODEX_API_KEY"}

def _judge_env():
    return {k: v for k, v in os.environ.items() if not k.startswith("GENUDO_") and k not in _JUDGE_ENV_DROP}

def _redact(verdict):
    reason = str(verdict.get("reason", ""))[:300]
    token = os.environ.get("GENUDO_TOKEN", "").removeprefix("Bearer ").strip()
    if token and len(token) >= 8:
        reason = reason.replace(token, "[redacted]")
    return {**verdict, "reason": reason}

def parse_verdict(out):
    """Tolerantly pull the first JSON object containing a verdict out of CLI stdout."""
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", out or ""):
        try:
            obj, _ = dec.raw_decode(out[m.start():])
        except ValueError:
            continue
        if isinstance(obj, dict) and str(obj.get("verdict", "")).lower() in ("pass", "fail"):
            return {"verdict": obj["verdict"].lower(), "reason": str(obj.get("reason", ""))}
    return None

def evaluate_with_llm(step, history, replies, facts, backend="claude"):
    """Tier-2 judge. Returns None when not applicable, {"verdict": pass|fail, "reason"} on success,
    or {"verdict": "judge_error", "reason"} on failure (the Tier-1 verdict then stands)."""
    if backend == "off" or not replies or not (step.get("judge_rubric") or step.get("expected_reply")):
        return None

    prompt = f"""You are a strict QA judge for a GenuDo conversational sales agent.

REFERENCE FACTS AND RULES:
{facts}

CONVERSATION SO FAR:
{history}

LATEST CUSTOMER MESSAGE: {step.get('customer_message') or '(image only)'}
AI REPLY (all messages sent in answer):
{chr(10).join('- ' + r for r in replies)}

EXPECTED BEHAVIOUR (reference): {step.get('expected_reply')}
RUBRIC: {step.get('judge_rubric') or 'Reply is consistent with expected behaviour and reference facts.'}

Decide if the reply satisfies the rubric and reference facts.
Fail it for: invented facts, wrong numbers/prices, contradicting reference, missing a required element, or forbidden behaviour.
Do not fail for wording differences, synonyms, or polite colloquial variations.
Do not use any tools. Return JSON only: {{"verdict": "pass" or "fail", "reason": "one short sentence"}}"""

    try:
        with tempfile.TemporaryDirectory() as empty_dir:
            cmd = _judge_cmd(backend)
            cmd[0] = shutil.which(cmd[0]) or cmd[0]  # Windows: resolves claude.cmd / codex.cmd
            proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace",
                                  timeout=JUDGE_TIMEOUT, cwd=empty_dir, env=_judge_env())
        verdict = parse_verdict(proc.stdout)
        if verdict:
            return _redact(verdict)
        detail = (proc.stderr or proc.stdout or "").strip().replace("\n", " ")[:160]
        return {"verdict": "judge_error", "reason": f"{backend} exit {proc.returncode}, no JSON verdict: {detail}"}
    except subprocess.TimeoutExpired:
        return {"verdict": "judge_error", "reason": f"{backend} judge timed out after {JUDGE_TIMEOUT}s"}
    except Exception as e:
        return {"verdict": "judge_error", "reason": f"{backend} judge failed: {str(e)[:120]}"}
