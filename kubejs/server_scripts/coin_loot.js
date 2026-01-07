// Coin Loot - Add KubeShop coins to world chest loot
//
// This system uses NeoForge Global Loot Modifiers with static JSON files.
// The actual loot modification is done via data files in:
//   - kubejs/data/neoforge/loot_modifiers/global_loot_modifiers.json
//   - kubejs/data/kubeshop/loot_modifiers/*.json
//   - kubejs/data/kubeshop/loot_table/coin_pool_*.json
//
// Tiers:
//   LOW      - Villages, igloos, shipwrecks (map/supply), ruined portals
//              Coins: $1, $10
//   MEDIUM   - Dungeons, pyramids, temples, outposts, mansions, mineshafts, buried treasure
//              Coins: $1, $10, $100
//   HIGH     - Strongholds, bastions, nether fortresses, underwater ruins
//              Coins: $1, $10, $100, $1,000
//   LEGENDARY - End cities, ancient cities
//              Coins: $1, $10, $100, $1,000, $10,000

console.info('[CoinLoot] Coin loot system active (static JSON files)')
