"""
Email service — sends schedule reminder when a student scans at the wrong class.
Uses standard smtplib (no extra deps). Configure via SMTP_* env vars.
"""
import asyncio
import logging
import smtplib
from datetime import date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

from app.config import settings

logger = logging.getLogger(__name__)

DAY_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DAY_FULL  = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _day_abbr(d: date) -> str:
    return DAY_ABBR[d.weekday()]


def _day_full(d: date) -> str:
    return DAY_FULL[d.weekday()]


def _classes_for_day(enrolled_classes: list, target_date: date) -> list:
    """Filter enrolled classes (plain dicts) that have sessions on target_date's weekday."""
    abbr = _day_abbr(target_date)
    result = []
    for cls in enrolled_classes:
        # supports both ORM objects and plain dicts
        if isinstance(cls, dict):
            sched = cls.get("schedule") or {}
        else:
            sched = cls.schedule or {}
        days = sched.get("days", [])
        if abbr in days:
            result.append(cls)
    return result


def _build_html(
    student_name: str,
    student_code: str,
    wrong_class_name: str,
    wrong_class_code: str,
    today: date,
    tomorrow: date,
    today_classes: list,
    tomorrow_classes: list,
) -> str:
    def class_rows(classes: list) -> str:
        if not classes:
            return "<tr><td colspan='4' style='color:#888;padding:8px 0;'>No classes scheduled</td></tr>"
        rows = ""
        for c in classes:
            # supports both ORM objects and plain dicts
            if isinstance(c, dict):
                name     = c.get("class_name", "")
                code     = c.get("class_code", "")
                room     = c.get("room") or "—"
                sched    = c.get("schedule") or {}
            else:
                name     = c.class_name
                code     = c.class_code
                room     = c.room or "—"
                sched    = c.schedule or {}
            time_str = ""
            if sched.get("start_time") and sched.get("end_time"):
                time_str = f"{sched['start_time']} – {sched['end_time']}"
            rows += f"""
            <tr>
              <td style="padding:8px 12px;border-bottom:1px solid #eee;">{name}</td>
              <td style="padding:8px 12px;border-bottom:1px solid #eee;font-family:monospace;">{code}</td>
              <td style="padding:8px 12px;border-bottom:1px solid #eee;">{room}</td>
              <td style="padding:8px 12px;border-bottom:1px solid #eee;">{time_str or '—'}</td>
            </tr>"""
        return rows

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;background:#f5f7fa;margin:0;padding:0;">
<div style="max-width:560px;margin:32px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.08);">

  <!-- Header -->
  <div style="background:linear-gradient(135deg,#2563eb,#7c3aed);padding:28px 32px;">
    <p style="margin:0;color:rgba(255,255,255,.75);font-size:13px;letter-spacing:.5px;text-transform:uppercase;">Smart Attendance System</p>
    <h1 style="margin:8px 0 0;color:#fff;font-size:22px;">⚠️ Wrong Class Detected</h1>
  </div>

  <!-- Body -->
  <div style="padding:28px 32px;">
    <p style="color:#374151;font-size:15px;margin:0 0 16px;">
      Hi <strong>{student_name}</strong> (<code style="background:#f3f4f6;padding:2px 6px;border-radius:4px;">{student_code}</code>),
    </p>
    <p style="color:#374151;font-size:15px;margin:0 0 24px;">
      Your face was recognized at the attendance kiosk for
      <strong style="color:#dc2626;">{wrong_class_name} ({wrong_class_code})</strong>,
      but you are <strong>not enrolled</strong> in that class.
      Please check your schedule below and go to the correct room.
    </p>

    <!-- Today -->
    <h2 style="font-size:16px;color:#1e40af;margin:0 0 8px;">📅 Today — {_day_full(today)}, {today.strftime('%d %b %Y')}</h2>
    <table style="width:100%;border-collapse:collapse;font-size:14px;color:#374151;margin-bottom:24px;">
      <thead>
        <tr style="background:#eff6ff;">
          <th style="text-align:left;padding:8px 12px;border-bottom:2px solid #bfdbfe;">Class</th>
          <th style="text-align:left;padding:8px 12px;border-bottom:2px solid #bfdbfe;">Code</th>
          <th style="text-align:left;padding:8px 12px;border-bottom:2px solid #bfdbfe;">Room</th>
          <th style="text-align:left;padding:8px 12px;border-bottom:2px solid #bfdbfe;">Time</th>
        </tr>
      </thead>
      <tbody>{class_rows(today_classes)}</tbody>
    </table>

    <!-- Tomorrow -->
    <h2 style="font-size:16px;color:#1e40af;margin:0 0 8px;">📅 Tomorrow — {_day_full(tomorrow)}, {tomorrow.strftime('%d %b %Y')}</h2>
    <table style="width:100%;border-collapse:collapse;font-size:14px;color:#374151;margin-bottom:24px;">
      <thead>
        <tr style="background:#eff6ff;">
          <th style="text-align:left;padding:8px 12px;border-bottom:2px solid #bfdbfe;">Class</th>
          <th style="text-align:left;padding:8px 12px;border-bottom:2px solid #bfdbfe;">Code</th>
          <th style="text-align:left;padding:8px 12px;border-bottom:2px solid #bfdbfe;">Room</th>
          <th style="text-align:left;padding:8px 12px;border-bottom:2px solid #bfdbfe;">Time</th>
        </tr>
      </thead>
      <tbody>{class_rows(tomorrow_classes)}</tbody>
    </table>

    <p style="color:#6b7280;font-size:13px;margin:0;">
      If you believe this is an error, please contact your administrator.<br>
      This is an automated message — please do not reply.
    </p>
  </div>

  <!-- Footer -->
  <div style="background:#f9fafb;padding:16px 32px;border-top:1px solid #e5e7eb;text-align:center;">
    <p style="margin:0;color:#9ca3af;font-size:12px;">Smart Attendance · AIoT System</p>
  </div>
</div>
</body>
</html>
"""


def _send_smtp_blocking(to_email: str, subject: str, html_body: str) -> None:
    """Blocking SMTP send — call via run_in_executor."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    msg["To"]      = to_email
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.sendmail(settings.SMTP_FROM_EMAIL, to_email, msg.as_string())


async def send_wrong_class_email(
    student_name: str,
    student_code: str,
    student_email: Optional[str],
    wrong_class_name: str,
    wrong_class_code: str,
    enrolled_classes: list,   # list of Class ORM objects
) -> None:
    """
    Fire-and-forget: send an email to the student with their next-2-days schedule.
    Silently skips if SMTP is disabled or student has no email.
    """
    if not settings.SMTP_ENABLED:
        logger.info("[EMAIL] SMTP disabled — skipping wrong-class email for %s", student_code)
        return
    if not student_email:
        logger.info("[EMAIL] No email for student %s — skipping", student_code)
        return

    today    = date.today()
    tomorrow = today + timedelta(days=1)
    today_classes    = _classes_for_day(enrolled_classes, today)
    tomorrow_classes = _classes_for_day(enrolled_classes, tomorrow)

    html = _build_html(
        student_name     = student_name,
        student_code     = student_code,
        wrong_class_name = wrong_class_name,
        wrong_class_code = wrong_class_code,
        today            = today,
        tomorrow         = tomorrow,
        today_classes    = today_classes,
        tomorrow_classes = tomorrow_classes,
    )

    subject = f"⚠️ Wrong Class — Schedule Reminder for {student_name}"

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            _send_smtp_blocking,
            student_email,
            subject,
            html,
        )
        logger.info("[EMAIL] Schedule reminder sent → %s (%s)", student_email, student_code)
    except Exception as e:
        logger.warning("[EMAIL] Failed to send to %s: %s", student_email, e)
