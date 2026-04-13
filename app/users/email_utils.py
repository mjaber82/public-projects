"""Email template rendering utilities."""

import os
from pathlib import Path
from django.conf import settings


def _get_template_path(template_name: str) -> str:
    """Get the absolute path to an email template file."""
    template_dir = Path(__file__).parent / "email_templates"
    template_path = template_dir / f"{template_name}.html"
    return str(template_path)


def _render_template(template_name: str, context: dict) -> str:
    """Render an HTML email template with the given context.

    Args:
            template_name: Name of the template (without .html extension)
            context: Dictionary of variables to substitute in the template

    Returns:
            Rendered HTML string
    """
    template_path = _get_template_path(template_name)

    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Email template not found: {template_name}")

    with open(template_path, "r", encoding="utf-8") as f:
        template_content = f.read()

    # Simple template variable substitution using {{ variable }} syntax
    for key, value in context.items():
        placeholder = "{{ " + key + " }}"
        template_content = template_content.replace(placeholder, str(value))

    return template_content


def render_welcome_email(
    first_name: str,
    msisdn: str,
    email: str,
    app_url: str = None,
) -> tuple[str, str]:
    """Render welcome email after registration.

    Returns:
            Tuple of (html_content, plain_text_content)
    """
    if not app_url:
        app_url = getattr(settings, "APP_URL", "https://digitalwallet.local")

    context = {
        "first_name": first_name or "User",
        "msisdn": msisdn,
        "email": email,
        "app_url": app_url,
    }

    html = _render_template("welcome", context)

    # Plain text fallback
    plain_text = f"""Welcome to Digital Wallet!

Hi {context["first_name"]},

Your Digital Wallet account has been successfully created.

Account details:
- Phone Number: {context["msisdn"]}
- Email: {context["email"]}

You can now log in and start using your digital wallets.

Best regards,
The Digital Wallet Team
"""

    return html, plain_text


def render_deactivation_email(
    first_name: str,
    deactivated_at: str,
    app_url: str = None,
) -> tuple[str, str]:
    """Render account deactivation confirmation email.

    Args:
            first_name: User's first name
            deactivated_at: Formatted date/time of deactivation
            app_url: Application URL for reactivation link

    Returns:
            Tuple of (html_content, plain_text_content)
    """
    if not app_url:
        app_url = getattr(settings, "APP_URL", "https://digitalwallet.local")

    context = {
        "first_name": first_name or "User",
        "deactivated_at": deactivated_at,
        "app_url": app_url,
    }

    html = _render_template("deactivation_confirmation", context)

    # Plain text fallback
    plain_text = f"""Your Account Has Been Deactivated

Hi {context["first_name"]},

This email confirms that your Digital Wallet account has been deactivated on {context["deactivated_at"]}.

What this means:
- Your account is now inactive
- You cannot access your wallets or perform transactions
- Your account can be reactivated at any time

If you did not perform this action, please contact support immediately.

Best regards,
The Digital Wallet Team
"""

    return html, plain_text


def render_email_change_email(
    first_name: str,
    new_email: str,
    changed_at: str,
) -> tuple[str, str]:
    """Render email change confirmation email.

    Args:
            first_name: User's first name
            new_email: The new email address
            changed_at: Formatted date/time of change

    Returns:
            Tuple of (html_content, plain_text_content)
    """
    context = {
        "first_name": first_name or "User",
        "new_email": new_email,
        "changed_at": changed_at,
    }

    html = _render_template("email_change_confirmation", context)

    # Plain text fallback
    plain_text = f"""Email Change Confirmed

Hi {context["first_name"]},

This email confirms that the primary email address for your Digital Wallet account has been successfully changed.

New Email Address: {context["new_email"]}
Change Date & Time: {context["changed_at"]}

If you did not make this change, please contact support immediately.

Best regards,
The Digital Wallet Team
"""

    return html, plain_text
