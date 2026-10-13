from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import TestCase
from uuid import uuid4

from apps.rankings.serializers import PublicRankingSerializer


class PublicRankingPrivacyTests(TestCase):
    def test_public_ranking_anonymizes_name_and_omits_user_identifiers(self):
        user_id = uuid4()
        profile = SimpleNamespace(full_name='Jordan Mwangi')
        trust_score = SimpleNamespace(overall_merit_score=83.5, tier='apex')
        user = SimpleNamespace(id=user_id, profile=profile, trust_score=trust_score)
        ranking = SimpleNamespace(
            id=uuid4(),
            user_id=user_id,
            user=user,
            profession='General Engineering',
            global_rank=3,
            profession_rank=1,
            country_rank=2,
            previous_global_rank=4,
            rank_movement=1,
            last_updated=datetime.now(timezone.utc),
        )

        data = PublicRankingSerializer(ranking).data

        self.assertEqual(data['full_name'], f'JM****{str(user_id).replace("-", "")[-2:].upper()}')
        self.assertNotIn('user', data)
        self.assertNotIn('avatar_url', data)
