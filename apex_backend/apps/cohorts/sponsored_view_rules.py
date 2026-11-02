SPONSORED_VIEW_REWARD_TIERS = {
    20: 100,
    40: 200,
    80: 400,
    160: 800,
    320: 1600,
}
SPONSORED_VIEW_CYCLE_SIZE = 10


def reward_for_fee(fee_kes):
    return SPONSORED_VIEW_REWARD_TIERS.get(fee_kes)
