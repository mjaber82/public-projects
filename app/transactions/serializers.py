from rest_framework import serializers

from .models import Transaction


class TransactionSerializer(serializers.ModelSerializer):
    from_wallet_id = serializers.CharField(source="from_wallet.wallet_id", read_only=True)
    to_wallet_id = serializers.CharField(source="to_wallet.wallet_id", read_only=True)
    sender_msisdn = serializers.CharField(source="from_wallet.user_account.user.msisdn", read_only=True)
    receiver_msisdn = serializers.CharField(source="to_wallet.user_account.user.msisdn", read_only=True)
    direction = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = [
            "public_id",
            "transaction_id",
            "transaction_type",
            "status",
            "amount",
            "currency",
            "from_wallet_id",
            "to_wallet_id",
            "sender_msisdn",
            "receiver_msisdn",
            "direction",
            "stripe_session_id",
            "payment_method_id",
            "card_brand",
            "card_last4",
            "reject_reason",
            "completed_dt",
            "rejected_dt",
            "revoked_dt",
            "created_dt",
            "updated_dt",
        ]
        read_only_fields = fields

    def get_direction(self, obj):
        wallet_id = self.context.get("wallet_id")
        if not wallet_id:
            return None
        if obj.from_wallet and str(obj.from_wallet.wallet_id) == wallet_id:
            return "DEBIT"
        if obj.to_wallet and str(obj.to_wallet.wallet_id) == wallet_id:
            return "CREDIT"
        return None


class TransferCreateSerializer(serializers.Serializer):
    sender_wallet_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    receiver_msisdn = serializers.CharField(max_length=20, required=False, allow_blank=True)
    receiver_wallet_id = serializers.UUIDField(required=False)


class TransactionActionSerializer(serializers.Serializer):
    key = serializers.UUIDField()


class RejectTransactionSerializer(serializers.Serializer):
    key = serializers.UUIDField()
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True)


class TopUpSessionSerializer(serializers.Serializer):
    wallet_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    currency = serializers.CharField(max_length=10, required=False, default="USD")
