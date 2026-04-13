from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField(source="user.public_id", read_only=True)
    related_tx_id = serializers.UUIDField(source="related_tx.public_id", read_only=True)

    class Meta:
        model = Notification
        fields = [
            "public_id",
            "user_id",
            "title",
            "body",
            "status",
            "read_dt",
            "expires_at",
            "event_type",
            "related_tx_id",
            "created_dt",
            "updated_dt",
        ]
        read_only_fields = [
            "public_id",
            "user_id",
            "read_dt",
            "expires_at",
            "related_tx_id",
            "created_dt",
            "updated_dt",
        ]


class NotificationActionSerializer(serializers.Serializer):
    key = serializers.UUIDField()
