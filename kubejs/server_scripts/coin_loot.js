// Coin Loot - Add KubeShop coins to world chest loot
//
// This system uses NeoForge Global Loot Modifiers with static JSON files.
// The actual loot modification is done via data files in:
//   - kubejs/data/neoforge/loot_modifiers/global_loot_modifiers.json
//   - kubejs/data/kubeshop/loot_modifiers/*.json
//   - kubejs/data/kubeshop/loot_table/coin_pool_*.json
//
// Lootr Compatibility: Works automatically - GLM applies at loot table level
//
// ============================================================================
// TIER SYSTEM
// ============================================================================
//
// LOW (8% chance) - Coins: $1, $10
//   Villages, igloos, shipwrecks (map/supply), ruined portals
//
// MEDIUM (10% chance) - Coins: $1, $10, $100
//   Dungeons, pyramids, temples, outposts, mansions, mineshafts, buried treasure
//   Trial Chambers: entrance, intersection_barrel, supply
//   Repurposed Structures: mansions, mineshafts
//
// HIGH (12% chance) - Coins: $1, $10, $100, $1,000
//   Strongholds, bastions, nether fortresses, underwater ruins
//   Trial Chambers: corridor, intersection, reward_common, reward_ominous_common
//   Apotheosis: chest_valuable, spawner_swarm
//
// LEGENDARY (15% chance) - Coins: $1, $10, $100, $1,000, $10,000
//   End cities, ancient cities
//   Trial Chambers: reward, reward_rare, reward_unique, reward_ominous_rare
//   Atum: pharaoh
//
// MYTHIC (20% chance, +1 bonus roll) - Coins: All with higher rare weights
//   Trial Chambers: reward_ominous, reward_ominous_unique
//   Apotheosis: spawner_brutal, spawner_brutal_rotate
//
// ============================================================================
// COVERED LOOT TABLES (61 total)
// ============================================================================
//
// VANILLA (54):
//   - 16 village variants
//   - igloo_chest, ruined_portal
//   - shipwreck_map, shipwreck_supply, shipwreck_treasure
//   - simple_dungeon, desert_pyramid, jungle_temple
//   - pillager_outpost, woodland_mansion, abandoned_mineshaft
//   - buried_treasure
//   - stronghold_corridor, stronghold_crossing, stronghold_library
//   - bastion_bridge, bastion_hoglin_stable, bastion_other, bastion_treasure
//   - nether_bridge
//   - underwater_ruin_big, underwater_ruin_small
//   - end_city_treasure
//   - ancient_city, ancient_city_ice_box
//   - trial_chambers/* (13 variants)
//
// MODDED (7):
//   - apotheosis:chests/chest_valuable
//   - apotheosis:chests/spawner_brutal
//   - apotheosis:chests/spawner_brutal_rotate
//   - apotheosis:chests/spawner_swarm
//   - atum:chests/pharaoh
//   - repurposed_structures:chests/mansions/birch
//   - repurposed_structures:chests/mineshafts/jungle
//
// ============================================================================

console.info('[CoinLoot] Coin loot system active - 61 loot tables covered')
