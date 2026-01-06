# ATM10 Server Scripts

Custom KubeJS scripts for ATM10 (All The Mods 10) Minecraft server.

## Project Structure

```
atm10/
├── KubeShop/           # Economy & Shop system
│   ├── kubejs/
│   │   └── server_scripts/
│   │       └── kubeshop.js
│   └── resourcepack/   # Optional coin textures
├── discord/            # Discord integration
│   └── kubejs/
│       └── server_scripts/
│           └── discord_command.js
└── rules/              # Server rules command
    └── kubejs/
        └── server_scripts/
            └── rules_command.js
```

## Installation

Copy contents of each `kubejs/` folder to the server's `kubejs/` folder:
```
<minecraft-instance>/kubejs/server_scripts/
```

## KubeShop Economy System

### Features
- Virtual wallet balance per player
- Physical coin items (withdraw/deposit)
- Player-to-player payments
- Sign-based shops (buy/sell)
- Transaction history
- Admin commands

### Coin Denominations
| Value | Item | CustomModelData |
|-------|------|-----------------|
| $1 | Paper | 719001 |
| $10 | Paper | 719010 |
| $100 | Paper | 719100 |
| $1000 | Paper | 719999 |
| $10000 | Paper | 710000 |

### Commands
- `/wallet balance` - Check balance
- `/wallet pay <player> <amount>` - Send money
- `/wallet withdraw <amount> [denomination]` - Get coins
- `/wallet deposit [amount]` - Deposit coins
- `/wallet top` - Leaderboard
- `/wallet history` - Transaction history
- `/wallet shop help` - Shop creation guide
- `/wallet admin` - Admin commands (OP only)

### Resource Pack (Optional)
For custom coin textures, configure `server.properties`:
```properties
resource-pack=https://YOUR-URL/kubeshop-resources.zip
resource-pack-sha1=<sha1-hash>
require-resource-pack=false
```

## Development

### KubeJS Version
- KubeJS 2101.7.2-build.348
- Minecraft 1.21.1
- NeoForge

### Reload Scripts
```
/kubejs reload server_scripts
```

### Test Commands
```
/wallet admin addbalance <player> 1000
/wallet withdraw 1234
/wallet deposit
```
