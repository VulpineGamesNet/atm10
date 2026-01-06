# ATM10 Server Scripts

Custom KubeJS scripts for [All The Mods 10](https://www.curseforge.com/minecraft/modpacks/all-the-mods-10) Minecraft server.

## Features

### KubeShop - Economy & Shop System
- Virtual wallet with persistent balance
- Physical coin items ($1, $10, $100, $1000, $10000)
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

1. Copy the contents of each `kubejs/server_scripts/` folder to your server's `kubejs/server_scripts/`

2. Reload scripts:
   ```
   /kubejs reload server_scripts
   ```

3. (Optional) For custom coin textures, host `KubeShop/resourcepack/kubeshop-resources.zip` and add to `server.properties`:
   ```properties
   resource-pack=https://your-url.com/kubeshop-resources.zip
   resource-pack-sha1=f663ccec389cba9c0d37087db95be25808fae8ac
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
