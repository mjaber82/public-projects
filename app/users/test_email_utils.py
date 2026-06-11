from django.test import SimpleTestCase, override_settings

from app.users.email_utils import (
    _get_template_path,
    _render_template,
    render_deactivation_email,
    render_email_change_email,
    render_welcome_email,
)


class GetTemplatePathTests(SimpleTestCase):
    def test_returns_path_with_html_extension(self) -> None:
        path = _get_template_path("welcome")
        self.assertTrue(path.endswith("welcome.html"))
        self.assertIn("email_templates", path)


class RenderTemplateTests(SimpleTestCase):
    def test_renders_template_with_context(self) -> None:
        html = _render_template(
            "welcome", {"first_name": "Alice", "msisdn": "+1234", "email": "a@b.com", "app_url": "http://test.local"}
        )
        self.assertIn("Alice", html)

    def test_raises_for_nonexistent_template(self) -> None:
        with self.assertRaises(FileNotFoundError):
            _render_template("nonexistent_template", {})


class RenderWelcomeEmailTests(SimpleTestCase):
    def test_returns_html_and_plain_text(self) -> None:
        html, plain = render_welcome_email("Bob", "+1555", "bob@test.com")
        self.assertIn("Bob", html)
        self.assertIn("Bob", plain)
        self.assertIn("+1555", plain)
        self.assertIn("bob@test.com", plain)

    def test_default_first_name(self) -> None:
        html, plain = render_welcome_email("", "+1555", "bob@test.com")
        self.assertIn("User", plain)

    @override_settings(APP_URL="https://custom.app")
    def test_custom_app_url(self) -> None:
        html, plain = render_welcome_email("Bob", "+1555", "bob@test.com", app_url="https://custom.app")
        self.assertIn("https://custom.app", html)


class RenderDeactivationEmailTests(SimpleTestCase):
    def test_returns_html_and_plain_text(self) -> None:
        html, plain = render_deactivation_email("Alice", "2024-01-15 10:00 UTC")
        self.assertIn("Alice", html)
        self.assertIn("Alice", plain)
        self.assertIn("2024-01-15 10:00 UTC", plain)

    def test_default_first_name(self) -> None:
        html, plain = render_deactivation_email("", "2024-01-15")
        self.assertIn("User", plain)

    def test_custom_app_url(self) -> None:
        html, plain = render_deactivation_email("Alice", "2024-01-15", app_url="https://myapp.com")
        self.assertIn("https://myapp.com", html)


class RenderEmailChangeEmailTests(SimpleTestCase):
    def test_returns_html_and_plain_text(self) -> None:
        html, plain = render_email_change_email("Charlie", "new@email.com", "2024-06-01 12:00 UTC")
        self.assertIn("Charlie", html)
        self.assertIn("Charlie", plain)
        self.assertIn("new@email.com", plain)
        self.assertIn("2024-06-01 12:00 UTC", plain)

    def test_default_first_name(self) -> None:
        html, plain = render_email_change_email("", "new@email.com", "2024-06-01")
        self.assertIn("User", plain)
