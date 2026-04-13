from rest_framework import serializers

from .models import Country, User


class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ["public_id", "name", "iso_2", "iso_phone_code"]


class UserSerializer(serializers.ModelSerializer):
    country = CountrySerializer(read_only=True)
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = [
            "public_id",
            "username",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "msisdn",
            "dob",
            "country",
            "is_active",
            "deactivated_at",
            "consent",
            "kyc_verified",
            "kyc_verified_dt",
            "email_notifications",
        ]
        read_only_fields = [
            "public_id",
            "country",
            "is_active",
            "deactivated_at",
            "kyc_verified",
            "kyc_verified_dt",
        ]


class VerifyAccountSerializer(serializers.Serializer):
    msisdn = serializers.CharField(max_length=20)


class OtpRequestSerializer(serializers.Serializer):
    msisdn = serializers.CharField(max_length=20)
    purpose = serializers.ChoiceField(choices=["REGISTER", "LOGIN"])
    recaptcha_token = serializers.CharField(max_length=4096, required=False, allow_blank=True)


class OtpVerifySerializer(serializers.Serializer):
    msisdn = serializers.CharField(max_length=20)
    verification_code = serializers.CharField(max_length=128)
    purpose = serializers.ChoiceField(choices=["REGISTER", "LOGIN"])


class RegistrationEmailRequestSerializer(serializers.Serializer):
    registration_token = serializers.CharField(max_length=255)
    email = serializers.EmailField()


class RegistrationEmailVerifySerializer(serializers.Serializer):
    registration_token = serializers.CharField(max_length=255)
    verification_code = serializers.CharField(max_length=128)


class CompleteRegistrationSerializer(serializers.Serializer):
    registration_token = serializers.CharField(max_length=255)
    passcode = serializers.CharField(max_length=4, min_length=4)
    device_id = serializers.CharField(max_length=100, required=False, allow_blank=True)


class LoginPasscodeSerializer(serializers.Serializer):
    login_token = serializers.CharField(max_length=255)
    passcode = serializers.CharField(max_length=4, min_length=4)
    device_id = serializers.CharField(max_length=100, required=False, allow_blank=True)


class RefreshTokenSerializer(serializers.Serializer):
    refresh_token = serializers.CharField()


class UnlockSessionSerializer(serializers.Serializer):
    session_id = serializers.UUIDField()
    passcode = serializers.CharField(max_length=4, min_length=4)


class UpdateProfileSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    username = serializers.CharField(max_length=50, required=False, allow_blank=True)
    email_notifications = serializers.BooleanField(required=False)


class StepUpRequestSerializer(serializers.Serializer):
    current_passcode = serializers.CharField(max_length=4, min_length=4)
    purpose = serializers.ChoiceField(choices=["CHANGE_PASSCODE", "CHANGE_PHONE", "CHANGE_EMAIL"])


class ChangePasscodeSerializer(serializers.Serializer):
    step_up_token = serializers.CharField(max_length=255)
    new_passcode = serializers.CharField(max_length=4, min_length=4)


class ChangePhoneSerializer(serializers.Serializer):
    step_up_token = serializers.CharField(max_length=255)
    new_msisdn = serializers.CharField(max_length=20)
    verification_code = serializers.CharField(max_length=128)


class ChangeEmailSerializer(serializers.Serializer):
    step_up_token = serializers.CharField(max_length=255)
    new_email = serializers.EmailField(required=True, allow_blank=False)
    verification_code = serializers.CharField(max_length=128, required=False, allow_blank=True)


class ForgotPasscodeStartSerializer(serializers.Serializer):
    msisdn = serializers.CharField(max_length=20)
    verification_code = serializers.CharField(max_length=128)


class ForgotPasscodeEmailVerifySerializer(serializers.Serializer):
    msisdn = serializers.CharField(max_length=20)
    email = serializers.EmailField()
    step_up_token_1 = serializers.CharField(max_length=255)
    verification_code = serializers.CharField(max_length=128)


class ForgotPasscodeCompleteSerializer(serializers.Serializer):
    msisdn = serializers.CharField(max_length=20)
    step_up_token_2 = serializers.CharField(max_length=255)
    new_passcode = serializers.CharField(max_length=4, min_length=4)


class NoSimRecoveryStartSerializer(serializers.Serializer):
    msisdn = serializers.CharField(max_length=20)
    passcode = serializers.CharField(max_length=4, min_length=4)


class NoSimRecoveryEmailVerifySerializer(serializers.Serializer):
    msisdn = serializers.CharField(max_length=20)
    step_up_token_1 = serializers.CharField(max_length=255)
    verification_code = serializers.CharField(max_length=128)


class NoSimRecoveryCompleteSerializer(serializers.Serializer):
    msisdn = serializers.CharField(max_length=20)
    step_up_token_2 = serializers.CharField(max_length=255)
    new_msisdn = serializers.CharField(max_length=20)
    verification_code = serializers.CharField(max_length=128)
