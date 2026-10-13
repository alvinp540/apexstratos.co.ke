from rest_framework import serializers
from .models import Ranking


class RankingSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='user.profile.full_name', read_only=True)
    avatar_url = serializers.CharField(source='user.profile.avatar_url', read_only=True)
    overall_merit_score = serializers.FloatField(
        source='user.trust_score.overall_merit_score', read_only=True
    )
    tier = serializers.CharField(source='user.trust_score.tier', read_only=True)

    class Meta:
        model = Ranking
        fields = (
            'id', 'user', 'full_name', 'avatar_url', 'profession',
            'global_rank', 'profession_rank', 'country_rank',
            'previous_global_rank', 'rank_movement',
            'overall_merit_score', 'tier', 'last_updated',
        )
        read_only_fields = fields


class PublicRankingSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    overall_merit_score = serializers.FloatField(
        source='user.trust_score.overall_merit_score', read_only=True
    )
    tier = serializers.CharField(source='user.trust_score.tier', read_only=True)

    class Meta:
        model = Ranking
        fields = (
            'id', 'full_name', 'profession', 'global_rank', 'profession_rank',
            'country_rank', 'previous_global_rank', 'rank_movement',
            'overall_merit_score', 'tier', 'last_updated',
        )
        read_only_fields = fields

    def get_full_name(self, obj):
        full_name = getattr(getattr(obj.user, 'profile', None), 'full_name', '') or ''
        initials = ''.join(part[0] for part in full_name.split() if part)
        suffix = str(obj.user_id).replace('-', '')[-2:].upper()
        return f'{initials[:2].upper()}****{suffix}' if initials else f'AP****{suffix}'
