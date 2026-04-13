from rest_framework_simplejwt.tokens import RefreshToken as SimpleJWTRefreshToken


class RefreshToken(SimpleJWTRefreshToken):
    """Custom token helper that embeds user and session identifiers."""

    @classmethod
    def for_user_session(cls, user, user_session):
        token = super().for_user(user)
        token["user_id"] = str(user.public_id)
        token["sid"] = str(user_session.public_id)
        return token
