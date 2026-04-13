from rest_framework import serializers

from .models import Wallet


class WalletSerializer(serializers.ModelSerializer):
    user_account_id = serializers.CharField(source="user_account.account_id", read_only=True)
    user_id = serializers.UUIDField(source="user_account.user.public_id", read_only=True)

    class Meta:
        model = Wallet
        fields = [
            "public_id",
            "wallet_id",
            "name",
            "balance",
            "in_transfer",
            "is_active",
            "is_main",
            "deactivated_at",
            "user_account_id",
            "user_id",
            "created_dt",
            "updated_dt",
        ]
        read_only_fields = [
            "public_id",
            "wallet_id",
            "balance",
            "in_transfer",
            "is_active",
            "is_main",
            "deactivated_at",
            "user_account_id",
            "user_id",
            "created_dt",
            "updated_dt",
        ]


class CreateWalletSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)


class UpdateWalletSerializer(serializers.Serializer):
    key = serializers.UUIDField()
    name = serializers.CharField(max_length=100)


class WalletActionSerializer(serializers.Serializer):
    key = serializers.UUIDField()
