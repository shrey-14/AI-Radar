"""
pipeline/alerting.py
====================
Sends styled HTML email alerts when the pipeline fails or succeeds.
Uses Gmail SMTP — free, no third-party service needed.

Required env vars:
    ALERT_EMAIL_FROM      your Gmail address (e.g. you@gmail.com)
    ALERT_EMAIL_PASSWORD  Gmail App Password (NOT your regular password)
                          Generate at: myaccount.google.com/apppasswords
    ALERT_EMAIL_TO        where to send alerts (can be same as FROM)
"""

import smtplib
import traceback
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone

from config import settings
import logging

log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
#  SHARED EMAIL CHROME — header + footer used by both templates
# ══════════════════════════════════════════════════════════════════

def _html_wrapper(status: str, status_color: str, badge_bg: str, inner_html: str) -> str:
    """
    Wraps any email body in the shared Signal Desk chrome —
    monospace terminal aesthetic, dark header, status badge.
    """
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>AI Radar Pipeline</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300..700&display=swap" rel="stylesheet">
</head>
<body style="margin:0;padding:0;background:#0d0f12;font-family:'Space Grotesk', sans-serif;">

  <!-- Outer wrapper -->
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0d0f12;padding:32px 16px;">
    <tr>
      <td align="center">
        <table width="620" cellpadding="0" cellspacing="0"
               style="max-width:620px;width:100%;background:#13161b;
                      border:1px solid #22262e;border-radius:4px;overflow:hidden;">

          <!-- ── Header bar ── -->
          <tr>
            <td style="background:#0d0f12;padding:20px 28px;
                       border-bottom:1px solid #22262e;">
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td>
                    <!-- Logo / wordmark -->
                    <span style="font-size:14px;font-weight:700;letter-spacing:0.18em;
                                 color:white;text-transform:uppercase;">
                      ◈ AI RADAR
                    </span>
                    <br/>
                    <span style="font-size:11px;letter-spacing:0.12em;color:#6c7280;
                                 text-transform:uppercase;">
                      Pipeline Monitor &nbsp;·&nbsp; The Signal Desk
                    </span>
                  </td>
                  <td align="right" valign="middle">
                    <!-- Status badge -->
                    <span style="display:inline-block;background:{badge_bg};
                                 color:{status_color};font-size:14px;font-weight:700;
                                 letter-spacing:0.12em;padding:5px 12px;
                                 border-radius:2px;text-transform:uppercase;">
                      {status}
                    </span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- ── Body ── -->
          <tr>
            <td style="padding:28px 28px 24px;">
              {inner_html}
            </td>
          </tr>

          <!-- ── Footer ── -->
          <tr>
            <td style="background:#0d0f12;padding:16px 28px;
                       border-top:1px solid #22262e;">
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td>
                    <span style="font-size:11px;color:#6c7280;letter-spacing:0.08em;">
                      AUTOMATED ALERT &nbsp;·&nbsp; AI RADAR PIPELINE
                    </span>
                  </td>
                  <td align="right">
                    <span style="font-size:11px;color:#6c7280;letter-spacing:0.08em;">
                      Check server logs for full output
                    </span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>

</body>
</html>"""


def _meta_row(label: str, value: str, value_color: str = "#c8cdd8") -> str:
    """Single key-value row in the metadata table."""
    return f"""
      <tr>
        <td style="padding:7px 0;border-bottom:1px solid #1c2028;font-size:12px;letter-spacing:0.1em;color:#4b5263;text-transform:uppercase;white-space:nowrap;padding-right:24px;width:1%;">
          {label}
        </td>
        <td style="padding:7px 0;border-bottom:1px solid #1c2028;font-size:12px;color:{value_color};">
          {value}
        </td>
      </tr>"""


def _section_header(title: str) -> str:
    return f"""
    <p style="margin:20px 0 10px;font-size:13px;font-weight:700;letter-spacing:0.14em;
              color:#4b5263;text-transform:uppercase;border-bottom:1px solid #1c2028;
              padding-bottom:8px;">
      {title}
    </p>"""


# ══════════════════════════════════════════════════════════════════
#  FAILURE EMAIL
# ══════════════════════════════════════════════════════════════════

def _build_failure_html(
    pipeline_name: str,
    error: Exception,
    context: str,
    now: str,
) -> str:
    tb_raw = traceback.format_exc() or "No traceback available"
    tb_escaped = (
        tb_raw
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
        .replace(" ", "&nbsp;")
    )
    error_msg = str(error).replace("<", "&lt;").replace(">", "&gt;")

    inner = f"""
    <!-- Alert banner -->
    <div style="background:#1f0f0f;border:1px solid #5c1a1a;border-left:3px solid #dc2626;
                border-radius:3px;padding:14px 18px;margin-bottom:24px;">
      <p style="margin:0 0 4px;font-size:14px;font-weight:700;letter-spacing:0.12em;
                color:#dc2626;text-transform:uppercase;">
        ✕ &nbsp;Pipeline Failure Detected
      </p>
      <p style="margin:0;font-size:12px;color:#e57373;line-height:1.5;">
        Your AI Radar pipeline stopped unexpectedly. Immediate attention required.
      </p>
    </div>

    <!-- Metadata table -->
    {_section_header("Run Details")}
    <table width="100%" cellpadding="0" cellspacing="0">
      {_meta_row("Pipeline", pipeline_name)}
      {_meta_row("Timestamp", now)}
      {_meta_row("Context", context or "No additional context")}
      {_meta_row("Error type", type(error).__name__, "#f87171")}
    </table>

    <!-- Error message -->
    {_section_header("Error Message")}
    <div style="background:#1a0f0f;border:1px solid #3f1515;border-radius:3px;
                padding:14px 16px;">
      <p style="margin:0;font-size:12px;color:#f87171;line-height:1.6;
                word-break:break-all;">
        {error_msg}
      </p>
    </div>

    <!-- Traceback -->
    {_section_header("Traceback")}
    <div style="background:#0d0f12;border:1px solid #22262e;border-radius:3px;
                padding:14px 16px;overflow:auto;max-height:260px;">
      <p style="margin:0;font-size:12px;color:#6c7280;line-height:1.7;
                word-break:break-all;">
        {tb_escaped}
      </p>
    </div>

    <!-- Action prompt -->
    {_section_header("Next Steps")}
    <div style="background:#111418;border:1px solid #22262e;border-radius:3px;
                padding:12px 16px;">
      <p style="margin:0;font-size:12px;color:#6c7280;letter-spacing:0.06em;
                line-height:1.7;">
        1 &nbsp;·&nbsp; SSH into your server and check the full pipeline logs<br/>
        2 &nbsp;·&nbsp; Verify API keys are valid (Groq, Jina, OpenRouter, Supabase)<br/>
        3 &nbsp;·&nbsp; Re-run manually: <span style="color:#818cf8;">python pipeline/flow.py</span><br/>
        4 &nbsp;·&nbsp; Check free tier rate limits if the error mentions quota
      </p>
    </div>
    """

    return _html_wrapper(
        status="FAILED",
        status_color="#dc2626",
        badge_bg="#1f0f0f",
        inner_html=inner,
    )


# ══════════════════════════════════════════════════════════════════
#  SUCCESS EMAIL
# ══════════════════════════════════════════════════════════════════

def _build_success_html(
    duration_seconds: float,
    section_counts: dict,
    now: str,
) -> str:
    minutes = duration_seconds / 60
    seconds = duration_seconds % 60

    # Build section rows
    section_rows = ""
    sections = ["papers", "news", "tools", "benchmarks", "talks"]
    for sec in sections:
        counts = section_counts.get(sec, {})
        new_n = counts.get("new", 0)
        summ_n = counts.get("summarised", 0)
        embed_n = counts.get("embedded", 0)
        # colour the counts green if > 0, dim if 0

        def _val(n: int) -> str:
            col = "#4ade80" if n > 0 else "#2d3340"
            return f'<span style="color:{col};">{n}</span>'

        section_rows += f"""
        <tr>
          <td style="padding:8px 0;border-bottom:1px solid #1c2028;
                     font-size:10px;letter-spacing:0.1em;color:#4b5263;
                     text-transform:uppercase;padding-right:20px;width:1%;">
            {sec}
          </td>
          <td style="padding:8px 0;border-bottom:1px solid #1c2028;
                     font-size:11px;color:#c8cdd8;text-align:center;width:1%;
                     padding-right:20px;">
            {_val(new_n)}
            <span style="color:#2d3340;">&nbsp;new</span>
          </td>
          <td style="padding:8px 0;border-bottom:1px solid #1c2028;
                     font-size:11px;color:#c8cdd8;text-align:center;width:1%;
                     padding-right:20px;">
            {_val(summ_n)}
            <span style="color:#2d3340;">&nbsp;summ.</span>
          </td>
          <td style="padding:8px 0;border-bottom:1px solid #1c2028;
                     font-size:11px;color:#c8cdd8;text-align:center;">
            {_val(embed_n)}
            <span style="color:#2d3340;">&nbsp;emb.</span>
          </td>
        </tr>"""

    inner = f"""
    <!-- Success banner -->
    <div style="background:#0a1a0f;border:1px solid #14532d;border-left:3px solid #16a34a;
                border-radius:3px;padding:14px 18px;margin-bottom:24px;">
      <p style="margin:0 0 4px;font-size:14px;font-weight:700;letter-spacing:0.12em;
                color:#16a34a;text-transform:uppercase;">
        ✓ &nbsp;Pipeline Completed Successfully
      </p>
      <p style="margin:0;font-size:12px;color:#86efac;line-height:1.5;">
        All sections scraped, summarised, evaluated, and embedded.
        Content is fresh and ready for the day.
      </p>
    </div>

    <!-- Run metadata -->
    {_section_header("Run Details")}
    <table width="100%" cellpadding="0" cellspacing="0">
      {_meta_row("Timestamp", now)}
      {_meta_row("Duration", f"{int(minutes)}m {int(seconds)}s")}
      {_meta_row("Status", "All tasks completed", "#4ade80")}
    </table>

    <!-- Section breakdown -->
    {_section_header("Section Breakdown")}
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td style="padding:6px 0;font-size:11px;letter-spacing:0.1em;color:#2d3340;
                   text-transform:uppercase;padding-right:20px;">
          Section
        </td>
        <td style="padding:6px 0;font-size:11px;letter-spacing:0.1em;color:#2d3340;
                   text-transform:uppercase;text-align:center;padding-right:20px;">
          New
        </td>
        <td style="padding:6px 0;font-size:11px;letter-spacing:0.1em;color:#2d3340;
                   text-transform:uppercase;text-align:center;padding-right:20px;">
          Summarised
        </td>
        <td style="padding:6px 0;font-size:11px;letter-spacing:0.1em;color:#2d3340;
                   text-transform:uppercase;text-align:center;">
          Embedded
        </td>
      </tr>
      {section_rows}
    </table>

    <!-- Pipeline stages -->
    {_section_header("Pipeline Stages")}
    <table width="100%" cellpadding="0" cellspacing="0">
      {''.join(f'''<tr>
            <td style = "padding:7px 0;border-bottom:1px solid #1c2028;font-size:11px;color:#4b5263;padding-right:16px;width:1%;white-space:nowrap;letter-spacing:0.08em;" >
              {stage}
            </td >
            <td style = "padding:7px 0;border-bottom:1px solid #1c2028;" >
              <span style ="font-size: 11px; background:  # 0a1a0f;color:#4ade80;padding: 2px 8px; letter-spacing: 0.1em;text-transform: uppercase; ">
                COMPLETED
              </span>
            </td>
          </tr>'''
          for stage in [
              "§01 &nbsp;Scrape &amp; Ingest",
              "§02 &nbsp;Summarise",
              "§03 &nbsp;Evaluate (LLM Judge)",
              "§04 &nbsp;Embed (Jina v3)",
          ])}
    </table>
    """

    return _html_wrapper(
        status="SUCCESS",
        status_color="#16a34a",
        badge_bg="#0a1a0f",
        inner_html=inner,
    )


# ══════════════════════════════════════════════════════════════════
#  PUBLIC SEND FUNCTIONS
# ══════════════════════════════════════════════════════════════════

def _send_email(subject: str, html_body: str) -> None:
    """Core send logic — shared by both failure and success paths."""
    from_addr = getattr(settings, "alert_email_from", None)
    password  = getattr(settings, "alert_email_password", None)
    to_addr   = getattr(settings, "alert_email_to", None)

    if not all([from_addr, password, to_addr]):
        log.warning(
            "Alert email not configured — set ALERT_EMAIL_FROM, "
            "ALERT_EMAIL_PASSWORD, ALERT_EMAIL_TO in .env to enable alerts."
        )
        return

    try:
        msg = MIMEMultipart("alternative")
        msg["From"]    = from_addr
        msg["To"]      = to_addr
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(from_addr, password)
            server.sendmail(from_addr, to_addr, msg.as_string())

        log.info(f"Alert sent to {to_addr} — {subject}")

    except Exception as e:
        # Never let alerting crash the error handler
        log.error(f"Failed to send alert email: {e}")


def send_failure_alert(
    pipeline_name: str,
    error: Exception,
    context: str = "",
) -> None:
    """
    Send a styled red failure alert email.
    Call this from your flow.py except block.
    """
    now     = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    subject = f"[AI Radar] ✕ Pipeline FAILED — {pipeline_name} — {now}"
    html    = _build_failure_html(pipeline_name, error, context, now)
    _send_email(subject, html)


def send_success_summary(
    run_duration_seconds: float,
    section_counts: dict,
) -> None:
    """
    Send a styled green success summary email.
    Call this at the end of a successful flow.py run.

    section_counts format:
    {
        "papers":     {"new": 12, "summarised": 10, "embedded": 10},
        "news":       {"new": 8,  "summarised": 8,  "embedded": 8},
        "tools":      {"new": 5,  "summarised": 5,  "embedded": 5},
        "benchmarks": {"new": 3,  "summarised": 3,  "embedded": 3},
        "talks":      {"new": 2,  "summarised": 2,  "embedded": 2},
    }
    """
    now     = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    subject = f"[AI Radar] ✓ Pipeline OK — {now}"
    html    = _build_success_html(run_duration_seconds, section_counts, now)
    _send_email(subject, html)