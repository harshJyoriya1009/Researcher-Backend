"""
Shared branded email template. Produces both a plain-text and an HTML version
of the same message so send_email() can send a proper multipart email.
"""
from dataclasses import dataclass


@dataclass
class EmailContent:
    subject: str
    text_body: str
    html_body: str


APP_NAME = "Researcher"
BRAND_COLOR = "#4f46e5"


def render_email(
    *,
    subject: str,
    recipient_name: str,
    heading: str,
    paragraphs: list[str],
    cta_text: str | None = None,
    cta_url: str | None = None,
    footer_note: str | None = None,
) -> EmailContent:
    greeting = f"Hi {recipient_name}," if recipient_name else "Hi,"

    text_lines = [greeting, ""]
    text_lines.extend(paragraphs)
    if cta_url:
        text_lines += ["", cta_text or "Continue:", cta_url]
    if footer_note:
        text_lines += ["", footer_note]
    text_lines += ["", f"— {APP_NAME}"]
    text_body = "\n".join(text_lines)

    paragraphs_html = "".join(
        f'<p style="margin:0 0 16px;line-height:1.6;color:#374151;">{p}</p>' for p in paragraphs
    )

    cta_html = ""
    if cta_url:
        cta_html = f"""
            <div style="text-align:center;margin:28px 0;">
              <a href="{cta_url}"
                 style="background:{BRAND_COLOR};color:#ffffff;text-decoration:none;
                        padding:12px 28px;border-radius:8px;font-weight:600;
                        display:inline-block;font-family:sans-serif;font-size:14px;">
                {cta_text or "Continue"}
              </a>
            </div>
    
            """

    footer_html = ""
    if footer_note:
        footer_html = f'<p style="font-size:13px;color:#6b7280;margin-top:24px;">{footer_note}</p>'

    html_body = f"""\
<!DOCTYPE html>
<html>
  <body style="margin:0;padding:0;background:#f4f4f5;font-family:-apple-system,Segoe UI,sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="padding:32px 16px;">
      <tr>
        <td align="center">
          <table width="100%" style="max-width:480px;background:#ffffff;border-radius:12px;
                                      padding:32px;box-shadow:0 1px 3px rgba(0,0,0,0.08);">
            <tr><td>
              <p style="font-weight:700;font-size:18px;color:{BRAND_COLOR};margin:0 0 24px;">{APP_NAME}</p>
              <h1 style="font-size:20px;color:#111827;margin:0 0 16px;">{heading}</h1>
              <p style="margin:0 0 16px;color:#374151;">{greeting}</p>
              {paragraphs_html}
              {cta_html}
              {footer_html}
            </td></tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""

    return EmailContent(subject=subject, text_body=text_body, html_body=html_body)
