"""
Report Generator for GenuDo Test Runs:
Generates a self-contained HTML report for a run (runs/<id>/report.html).
"""

import os
import json
import html

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>GenuDo Test Run Report - {run_id}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 24px; background: #f8fafc; color: #1e293b; }}
  .header {{ background: #1e3a8a; color: white; padding: 24px; border-radius: 8px; margin-bottom: 24px; }}
  .header h1 {{ margin: 0 0 8px 0; font-size: 24px; }}
  .stats {{ display: flex; gap: 16px; margin-top: 16px; }}
  .stat-card {{ background: rgba(255,255,255,0.12); padding: 12px 20px; border-radius: 6px; min-width: 120px; }}
  .stat-val {{ font-size: 22px; font-weight: bold; }}
  .stat-lbl {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; opacity: 0.8; }}
  .case {{ background: white; border: 1px solid #e2e8f0; border-radius: 8px; margin-bottom: 16px; overflow: hidden; }}
  .case-header {{ padding: 14px 20px; background: #f1f5f9; display: flex; justify-content: space-between; align-items: center; font-weight: 600; cursor: pointer; }}
  .badge {{ padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: bold; text-transform: uppercase; }}
  .badge-pass {{ background: #dcfce7; color: #15803d; }}
  .badge-fail {{ background: #fee2e2; color: #b91c1c; }}
  .badge-warn, .badge-error {{ background: #fef3c7; color: #b45309; }}
  .case-body {{ padding: 20px; display: flex; flex-direction: column; gap: 16px; }}
  .step {{ border-left: 3px solid #cbd5e1; padding-left: 16px; margin-bottom: 12px; }}
  .step.pass {{ border-left-color: #22c55e; }}
  .step.fail {{ border-left-color: #ef4444; }}
  .step.warn {{ border-left-color: #f59e0b; }}
  .judge {{ font-size: 12px; color: #334155; margin-top: 6px; }}
  .step-customer {{ font-weight: 600; color: #0369a1; margin-bottom: 6px; }}
  .step-agent {{ background: #f8fafc; border: 1px solid #e2e8f0; padding: 10px; border-radius: 6px; margin-bottom: 8px; white-space: pre-wrap; }}
  .checks {{ display: flex; flex-wrap: wrap; gap: 6px; font-size: 12px; }}
  .check-tag {{ padding: 2px 8px; border-radius: 4px; }}
  .check-ok {{ background: #dcfce7; color: #166534; }}
  .check-bad {{ background: #fee2e2; color: #991b1b; font-weight: bold; }}
  .actions-list {{ font-size: 12px; color: #64748b; margin-top: 6px; }}
</style>
</head>
<body>
  <div class="header">
    <h1>GenuDo Agent Test Run: {run_id}</h1>
    <div>Generated: {timestamp} | Target Base: {base_url}</div>
    <div class="stats">
      <div class="stat-card"><div class="stat-val">{total_cases}</div><div class="stat-lbl">Total Journeys</div></div>
      <div class="stat-card"><div class="stat-val" style="color: #4ade80;">{passed_cases}</div><div class="stat-lbl">Passed</div></div>
      <div class="stat-card"><div class="stat-val" style="color: #f87171;">{failed_cases}</div><div class="stat-lbl">Failed</div></div>
      <div class="stat-card"><div class="stat-val">{p0_pass_rate}%</div><div class="stat-lbl">P0 Pass Rate</div></div>
    </div>
  </div>

  <div class="cases-container">
    {cases_html}
  </div>
</body>
</html>
"""

def generate_html_report(results_data, output_path):
    cases = results_data.get("cases", [])
    total = len(cases)
    passed = sum(1 for c in cases if c.get("verdict") == "pass")
    failed = sum(1 for c in cases if c.get("verdict") == "fail")
    p0_cases = [c for c in cases if c.get("priority") == "P0"]
    p0_passed = sum(1 for c in p0_cases if c.get("verdict") == "pass")
    p0_rate = round((p0_passed / len(p0_cases) * 100), 1) if p0_cases else 100.0

    cases_html = []
    for c in cases:
        verdict = c.get("verdict", "fail").lower()
        badge_cls = f"badge-{verdict}"
        steps_html = []
        for s in c.get("steps", []):
            st_verdict = s.get("verdict", "pass").lower()
            checks_tags = []
            for ch in s.get("checks", []):
                cls = "check-ok" if ch.get("ok") else "check-bad"
                mark = "✔" if ch.get("ok") else "✖"
                checks_tags.append(f'<span class="check-tag {cls}">{mark} {html.escape(ch.get("name", ""))}</span>')

            agent_replies = "<br>".join(html.escape(r) for r in s.get("replies", [])) or "<em>(No reply)</em>"
            actions_text = ", ".join(s.get("actions", [])) or "none"
            j = s.get("judge") or {}
            judge_html = f'<div class="judge">LLM judge: <b>{html.escape(str(j.get("verdict")))}</b> - {html.escape(str(j.get("reason", "")))}</div>' if j else ""

            steps_html.append(f"""
            <div class="step {st_verdict}">
              <div class="step-customer">Customer (Step {s.get('step')}): {html.escape(s.get('customer_message', ''))}</div>
              <div class="step-agent">{agent_replies}</div>
              <div class="checks">{''.join(checks_tags)}</div>
              <div class="actions-list">Fired Actions: <code>{html.escape(actions_text)}</code> | Stage: <code>{html.escape(str(s.get('stage') or '-'))}</code></div>
              {judge_html}
            </div>
            """)

        cases_html.append(f"""
        <div class="case">
          <div class="case-header">
            <span>{html.escape(c.get('case_id', ''))} - {html.escape(c.get('short_name', ''))} ({html.escape(c.get('pipeline', ''))}) [{html.escape(c.get('priority', ''))}]</span>
            <span class="badge {badge_cls}">{verdict}</span>
          </div>
          <div class="case-body">
            <p><em>{html.escape(c.get('description', ''))}</em></p>
            {f'<p><b>Error:</b> {html.escape(c["error"])}</p>' if c.get('error') else ''}
            {''.join(steps_html)}
          </div>
        </div>
        """)

    content = HTML_TEMPLATE.format(
        run_id=results_data.get("run_id", "Run"),
        timestamp=results_data.get("timestamp", ""),
        base_url=results_data.get("base_url", "https://api.genudo.ai"),
        total_cases=total,
        passed_cases=passed,
        failed_cases=failed,
        p0_pass_rate=p0_rate,
        cases_html="".join(cases_html)
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"HTML Report generated at {output_path}")
