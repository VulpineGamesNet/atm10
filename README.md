# ATM10 Server Scripts

Custom KubeJS scripts for [All The Mods 10](https://www.curseforge.com/minecraft/modpacks/all-the-mods-10) Minecraft server.

## Features

### KubeShop - Economy & Shop System
- Virtual wallet with persistent balance
- Physical coin items with Minecraft rarity colors:
  - $1 (Common - White)
  - $10 (Uncommon - Green)
  - $100 (Rare - Blue)
  - $1,000 (Epic - Light Purple)
  - $10,000 (Legendary - Gold)
- Player-to-player payments
- Sign-based chest shops (buy & sell)
- Transaction history
- Leaderboard
- Admin tools

### Discord Integration
- `/discord` command for server invite link

### Rules
- `/rules` command to display server rules

## Installation

1. Copy `kubejs/` folder to your Minecraft instance
2. Copy `resourcepacks/vulpinegames-resources/` to your instance's `resourcepacks/` folder
3. Reload scripts: `/kubejs reload server_scripts`
4. Enable the resource pack in-game (Options → Resource Packs)

### Server Resource Pack (Optional)
To auto-push textures to players, add to `server.properties`:
```properties
resource-pack=https://github.com/VulpineGamesNet/atm10/releases/download/v1.1.0/vulpinegames-resources.zip
resource-pack-sha1=94f876b7f44a650eaba7f5c2b053390aab49a6f6
```

## Commands

| Command | Description |
|---------|-------------|
| `/wallet` | Show wallet help |
| `/wallet balance` | Check your balance |
| `/wallet pay <player> <amount>` | Send money to player |
| `/wallet withdraw <amount>` | Withdraw as coins |
| `/wallet deposit` | Deposit all coins |
| `/wallet top` | Richest players |
| `/wallet history` | Transaction history |
| `/wallet shop help` | How to create shops |
| `/discord` | Server Discord invite |
| `/rules` | Server rules |

## Requirements

- Minecraft 1.21.1
- NeoForge
- KubeJS 2101.7.x

## License

MIT
