from rest_framework import serializers
from .models import ChatSession


class ChatSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatSession
        fields = ['id', 'title', 'created_at', 'updated_at', 'payload']

    def to_representation(self, instance):
        data = dict(instance.payload or {})
        data.update({
            'id': instance.id,
            'title': instance.title,
            'createdAt': instance.created_at,
            'updatedAt': instance.updated_at,
        })
        return data
