# ATM10 Server Scripts

Custom KubeJS scripts for ATM10 (All The Mods 10) Minecraft server.

## Commit Convention

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]
```

### Types
- `feat` - New feature
- `fix` - Bug fix
- `docs` - Documentation only
- `refactor` - Code change that neither fixes a bug nor adds a feature
- `chore` - Maintenance tasks

### Scopes
- `kubeshop` - Economy & shop system
- `discord` - Discord integration
- `rules` - Server rules
- `resourcepack` - Coin textures

### Examples
```
feat(kubeshop): add coin deposit command
fix(kubeshop): fix balance not saving on server restart
docs: update README with installation steps
refactor(kubeshop): simplify coin detection logic
```

## Project Structure

```
atm10/
├── kubejs/
│   └── server_scripts/
│       ├── kubeshop.js         # Economy & shop system
│       ├── discord_command.js  # Discord integration
│       └── rules_command.js    # Server rules
└── resourcepacks/
    └── vulpinegames-resources/ # Custom coin textures
```

## Installation

Copy the `kubejs/` and `resourcepacks/` folders to your Minecraft instance:
```
<minecraft-instance>/kubejs/
<minecraft-instance>/resourcepacks/
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

### KubeJS 1.21 Component System
In Minecraft 1.21+, items use data components instead of NBT. Do NOT use `setNbt()`.

Use component syntax:
```javascript
// Creating items with components
let item = Item.of('minecraft:gold_nugget[minecraft:custom_model_data=123,minecraft:custom_name=\'{"text":"Coin"}\']')

// Or build the string
let itemString = 'minecraft:gold_nugget[' +
  'minecraft:custom_model_data=' + customModelData + ',' +
  'minecraft:custom_name=\'' + jsonName + '\'' +
  ']'
let item = Item.of(itemString).withCount(count)
```

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
