// KubeShop - Complete Economy & Shop System
// Single file to avoid KubeJS scope issues between scripts

// ============================================================================
// CONFIGURATION
// ============================================================================

const STARTING_BALANCE = 0
const ROOT_KEY = "kubeshop"  // All data stored under this key in server.persistentData
const MAX_HISTORY_PER_PLAYER = 50

// Sub-keys within the root
const BALANCES_KEY = "balances"
const SHOPS_KEY = "shops"
const HISTORY_KEY = "history"
const BYPASS_KEY = "bypass"

// Coin denominations for withdraw/deposit (ordered largest to smallest for greedy algorithm)
// Uses vanilla paper items with CustomModelData NBT for server-side only implementation
const COIN_BASE_ITEM = 'minecraft:sunflower'
const COIN_DENOMINATIONS = [
  { value: 10000, customModelData: 710000, name: 'Coin', lore: 'Worth $10,000', color: 'gold' },
  { value: 1000,  customModelData: 719999, name: 'Coin', lore: 'Worth $1,000',  color: 'light_purple' },
  { value: 100,   customModelData: 719100, name: 'Coin', lore: 'Worth $100',    color: 'blue' },
  { value: 10,    customModelData: 719010, name: 'Coin', lore: 'Worth $10',     color: 'green' },
  { value: 1,     customModelData: 719001, name: 'Coin', lore: 'Worth $1',      color: 'white' }
]

// ============================================================================
// IN-MEMORY CACHES
// ============================================================================

let balancesCache = {}
let shopsCache = {}
let historyCache = {}
let dataLoaded = false

// ============================================================================
// DATA LOADING - Ensures data is loaded (lazy loading for /reload support)
// ============================================================================

// Get or create the root kubeshop NBT compound
function getRootNbt(server) {
  if (!server.persistentData.contains(ROOT_KEY)) {
    server.persistentData.put(ROOT_KEY, NBT.compoundTag())
  }
  return server.persistentData.getCompound(ROOT_KEY)
}

function ensureDataLoaded(server) {
  if (dataLoaded) return

  console.info("[KubeShop] Loading data (lazy load)...")
  loadBalances(server)
  loadShops(server)
  loadHistory(server)
  dataLoaded = true
}

// ============================================================================
// CURRENCY SYSTEM - Data Persistence
// ============================================================================

function loadBalances(server) {
  let rootNbt = getRootNbt(server)

  if (!rootNbt.contains(BALANCES_KEY)) {
    rootNbt.put(BALANCES_KEY, NBT.compoundTag())
  }
  let balNbt = rootNbt.getCompound(BALANCES_KEY)

  balancesCache = {}

  let keySet = balNbt.getAllKeys().toArray()
  for (let i = 0; i < keySet.length; i++) {
    let id = keySet[i]
    balancesCache[id] = balNbt.getInt(id)
  }
  console.info("[KubeShop] Loaded " + keySet.length + " balance entries")
}

function saveBalance(server, playerUuid) {
  let rootNbt = getRootNbt(server)
  if (!rootNbt.contains(BALANCES_KEY)) {
    rootNbt.put(BALANCES_KEY, NBT.compoundTag())
  }
  rootNbt.getCompound(BALANCES_KEY).putInt(playerUuid, balancesCache[playerUuid])
}

function ensurePlayer(server, uuid) {
  if (balancesCache[uuid] === undefined) {
    balancesCache[uuid] = STARTING_BALANCE
    saveBalance(server, uuid)
  }
}

// ============================================================================
// CURRENCY SYSTEM - API Functions
// ============================================================================

function getBalance(server, uuid) {
  ensureDataLoaded(server)
  ensurePlayer(server, uuid)
  return balancesCache[uuid]
}

function setBalance(server, uuid, amount) {
  ensureDataLoaded(server)
  if (amount < 0) return false
  balancesCache[uuid] = Math.floor(amount)
  saveBalance(server, uuid)
  return true
}

function addBalance(server, uuid, amount) {
  ensureDataLoaded(server)
  if (amount < 0) return false
  ensurePlayer(server, uuid)
  balancesCache[uuid] += Math.floor(amount)
  saveBalance(server, uuid)
  return true
}

function removeBalance(server, uuid, amount) {
  ensureDataLoaded(server)
  if (amount < 0) return false
  ensurePlayer(server, uuid)
  let toRemove = Math.floor(amount)
  if (balancesCache[uuid] < toRemove) return false
  balancesCache[uuid] -= toRemove
  saveBalance(server, uuid)
  return true
}

function hasBalance(server, uuid, amount) {
  ensureDataLoaded(server)
  ensurePlayer(server, uuid)
  return balancesCache[uuid] >= Math.floor(amount)
}

function formatBalance(amount) {
  return "$" + amount
}

// ============================================================================
// SHOP SYSTEM - Data Persistence
// ============================================================================

function loadShops(server) {
  let rootNbt = getRootNbt(server)

  if (!rootNbt.contains(SHOPS_KEY)) {
    rootNbt.put(SHOPS_KEY, NBT.compoundTag())
  }

  shopsCache = {}
  let shopsNbt = rootNbt.getCompound(SHOPS_KEY)
  let keys = shopsNbt.getAllKeys().toArray()

  for (let i = 0; i < keys.length; i++) {
    let key = keys[i]
    let shopNbt = shopsNbt.getCompound(key)
    shopsCache[key] = {
      owner: shopNbt.getString("owner"),
      chestPos: shopNbt.getString("chestPos"),
      type: shopNbt.getString("type"),
      price: shopNbt.getInt("price"),
      itemTemplate: shopNbt.getString("itemTemplate")
    }
  }
}

function saveShop(server, signKey, shopData) {
  let rootNbt = getRootNbt(server)
  if (!rootNbt.contains(SHOPS_KEY)) {
    rootNbt.put(SHOPS_KEY, NBT.compoundTag())
  }

  let shopNbt = NBT.compoundTag()
  shopNbt.putString("owner", shopData.owner)
  shopNbt.putString("chestPos", shopData.chestPos)
  shopNbt.putString("type", shopData.type)
  shopNbt.putInt("price", shopData.price)
  shopNbt.putString("itemTemplate", shopData.itemTemplate)

  rootNbt.getCompound(SHOPS_KEY).put(signKey, shopNbt)
  shopsCache[signKey] = shopData
}

function removeShop(server, signKey) {
  let rootNbt = getRootNbt(server)
  if (rootNbt.contains(SHOPS_KEY)) {
    rootNbt.getCompound(SHOPS_KEY).remove(signKey)
  }
  delete shopsCache[signKey]
}

function getShop(signKey) {
  return shopsCache[signKey] || null
}

// ============================================================================
// TRANSACTION HISTORY SYSTEM
// ============================================================================

function loadHistory(server) {
  let rootNbt = getRootNbt(server)

  if (!rootNbt.contains(HISTORY_KEY)) {
    rootNbt.put(HISTORY_KEY, NBT.compoundTag())
  }

  historyCache = {}
  let historyNbt = rootNbt.getCompound(HISTORY_KEY)
  let keys = historyNbt.getAllKeys().toArray()

  for (let i = 0; i < keys.length; i++) {
    let playerUuid = keys[i]
    let playerHistoryStr = historyNbt.getString(playerUuid)
    try {
      historyCache[playerUuid] = JSON.parse(playerHistoryStr)
    } catch(e) {
      historyCache[playerUuid] = []
    }
  }
  console.info("[KubeShop] Loaded history for " + keys.length + " players")
}

function saveHistory(server, playerUuid) {
  let rootNbt = getRootNbt(server)
  if (!rootNbt.contains(HISTORY_KEY)) {
    rootNbt.put(HISTORY_KEY, NBT.compoundTag())
  }
  let history = historyCache[playerUuid] || []
  rootNbt.getCompound(HISTORY_KEY).putString(playerUuid, JSON.stringify(history))
}

// Transaction types: "pay_sent", "pay_received", "shop_buy", "shop_sell", "admin_set", "admin_add", "admin_subtract"
function addHistoryEntry(server, playerUuid, type, amount, otherPlayer, description) {
  ensureDataLoaded(server)
  if (!historyCache[playerUuid]) {
    historyCache[playerUuid] = []
  }

  let entry = {
    type: type,
    amount: amount,
    other: otherPlayer || null,
    desc: description || null,
    time: Date.now()
  }

  historyCache[playerUuid].unshift(entry)

  // Trim to max entries
  if (historyCache[playerUuid].length > MAX_HISTORY_PER_PLAYER) {
    historyCache[playerUuid] = historyCache[playerUuid].slice(0, MAX_HISTORY_PER_PLAYER)
  }

  saveHistory(server, playerUuid)
}

function getHistory(server, playerUuid) {
  ensureDataLoaded(server)
  return historyCache[playerUuid] || []
}

function formatTimestamp(timestamp) {
  let date = new Date(timestamp)
  let month = date.getMonth() + 1
  let day = date.getDate()
  let hours = date.getHours()
  let minutes = date.getMinutes()
  return (month < 10 ? "0" : "") + month + "/" +
         (day < 10 ? "0" : "") + day + " " +
         (hours < 10 ? "0" : "") + hours + ":" +
         (minutes < 10 ? "0" : "") + minutes
}

// ============================================================================
// COIN SYSTEM - Helper Functions (NBT-based paper items)
// ============================================================================

// Create a coin item with proper components (1.21+ format)
function createCoinItem(denom, count) {
  // Use the new 1.21 component syntax: item[component=value,...]
  // custom_name uses JSON text component format
  // lore uses JSON array of text components
  // Note: In 1.21.1, custom_model_data is still a simple integer
  // In 1.21.4+, it becomes a complex structure with floats/flags/strings/colors
  let itemString = COIN_BASE_ITEM + '[' +
    'minecraft:custom_model_data=' + denom.customModelData + ',' +
    'minecraft:custom_name=\'{"text":"' + denom.name + '","color":"' + denom.color + '","italic":false}\',' +
    'minecraft:lore=[\'{"text":"' + denom.lore + '","color":"gray","italic":false}\']' +
    ']'
  return Item.of(itemString).withCount(count)
}

// Get the CustomModelData from an item stack (returns 0 if not present)
// In 1.21+, custom_model_data is a data component, not NBT
function getItemCustomModelData(stack) {
  if (!stack || stack.isEmpty()) return 0

  // Try 1.21+ component access first
  try {
    // In 1.21, use the components API
    let customModelData = stack.get('custom_model_data')
    if (customModelData !== null && customModelData !== undefined) {
      // customModelData can be an integer or an object with value property
      if (typeof customModelData === 'number') return customModelData
      if (customModelData.value) return customModelData.value
      return customModelData
    }
  } catch(e) {
    // Fall through to legacy method
  }

  // Fallback: try legacy NBT access (pre-1.21)
  try {
    let nbt = stack.getNbt()
    if (!nbt) return 0
    if (nbt.contains && !nbt.contains('CustomModelData')) return 0
    return nbt.getInt ? nbt.getInt('CustomModelData') : 0
  } catch(e) {
    return 0
  }
}

// Get the coin denomination info from an item stack (returns null if not a coin)
function getCoinDenomFromStack(stack) {
  if (!stack || stack.isEmpty()) return null
  if (stack.getId() !== COIN_BASE_ITEM) return null

  let customModelData = getItemCustomModelData(stack)
  if (customModelData === 0) return null

  for (let i = 0; i < COIN_DENOMINATIONS.length; i++) {
    if (COIN_DENOMINATIONS[i].customModelData === customModelData) {
      return COIN_DENOMINATIONS[i]
    }
  }
  return null
}

// Get the value of a coin item stack (returns 0 if not a coin)
function getCoinValue(stack) {
  let denom = getCoinDenomFromStack(stack)
  return denom ? denom.value : 0
}

// Count all coins in player inventory and return total value + breakdown
function countPlayerCoins(player) {
  let inv = player.getInventory()
  let slots = inv.getSlots ? inv.getSlots() : (inv.size ? inv.size() : 36)
  let total = 0
  let breakdown = {}

  // Initialize breakdown with customModelData keys
  for (let i = 0; i < COIN_DENOMINATIONS.length; i++) {
    breakdown[COIN_DENOMINATIONS[i].customModelData] = 0
  }

  for (let i = 0; i < slots; i++) {
    let stack = inv.getStackInSlot ? inv.getStackInSlot(i) : inv.getItem(i)
    if (stack && !stack.isEmpty()) {
      let denom = getCoinDenomFromStack(stack)
      if (denom) {
        let count = stack.getCount()
        total += denom.value * count
        breakdown[denom.customModelData] = (breakdown[denom.customModelData] || 0) + count
      }
    }
  }

  return { total: total, breakdown: breakdown }
}

// Give coins to player using greedy algorithm (fewest coins possible)
// Note: If inventory is full, items will drop on the ground
function giveCoinsEfficient(player, amount) {
  let remaining = amount

  for (let i = 0; i < COIN_DENOMINATIONS.length; i++) {
    let denom = COIN_DENOMINATIONS[i]
    if (remaining >= denom.value) {
      let count = Math.floor(remaining / denom.value)
      remaining = remaining % denom.value

      // Give in stacks of 64
      while (count > 0) {
        let stackSize = Math.min(count, 64)
        player.give(createCoinItem(denom, stackSize))
        count -= stackSize
      }
    }
  }
}

// Give coins of a specific denomination
function giveCoinsSpecific(player, amount, denomination) {
  let denomInfo = null
  for (let i = 0; i < COIN_DENOMINATIONS.length; i++) {
    if (COIN_DENOMINATIONS[i].value === denomination) {
      denomInfo = COIN_DENOMINATIONS[i]
      break
    }
  }

  if (!denomInfo) return false
  if (amount % denomination !== 0) return false

  let count = amount / denomination

  // Give in stacks of 64
  while (count > 0) {
    let stackSize = Math.min(count, 64)
    player.give(createCoinItem(denomInfo, stackSize))
    count -= stackSize
  }

  return true
}

// Remove coins from player inventory worth the specified amount (greedy, largest first)
// IMPORTANT: This function requires exact change - use canPayExactWithCoins() to check first
function removeCoinsFromPlayer(player, amount) {
  // Pre-check: verify exact payment is possible
  if (!canPayExactWithCoins(player, amount)) return false

  let inv = player.getInventory()
  let slots = inv.getSlots ? inv.getSlots() : (inv.size ? inv.size() : 36)
  let remaining = amount

  // Process largest denominations first
  for (let d = 0; d < COIN_DENOMINATIONS.length && remaining > 0; d++) {
    let denom = COIN_DENOMINATIONS[d]

    for (let i = 0; i < slots && remaining > 0; i++) {
      let stack = inv.getStackInSlot ? inv.getStackInSlot(i) : inv.getItem(i)
      let stackDenom = getCoinDenomFromStack(stack)
      if (stackDenom && stackDenom.customModelData === denom.customModelData) {
        let stackCount = stack.getCount()
        let maxCanUse = Math.floor(remaining / denom.value)
        let toRemove = Math.min(stackCount, maxCanUse)

        if (toRemove > 0) {
          // Properly update inventory - shrink and set back to ensure update
          stack.shrink(toRemove)
          if (stack.isEmpty()) {
            inv.setItem(i, Item.empty())
          } else {
            inv.setItem(i, stack)
          }
          remaining -= toRemove * denom.value
        }
      }
    }
  }

  return remaining === 0
}

// Check if player can pay exact amount with their coins
function canPayExactWithCoins(player, amount) {
  let coinInfo = countPlayerCoins(player)
  if (coinInfo.total < amount) return false

  // Greedy check - simulate removal
  let remaining = amount
  for (let d = 0; d < COIN_DENOMINATIONS.length && remaining > 0; d++) {
    let denom = COIN_DENOMINATIONS[d]
    let available = coinInfo.breakdown[denom.customModelData] || 0
    let maxCanUse = Math.floor(remaining / denom.value)
    let toUse = Math.min(available, maxCanUse)
    remaining -= toUse * denom.value
  }

  return remaining === 0
}

// ============================================================================
// BLOCK HELPER FUNCTIONS
// ============================================================================

function getBlockKey(block) {
  let pos = block.getPos()
  let dim = block.getLevel().getDimension().toString()
  return pos.getX() + "_" + pos.getY() + "_" + pos.getZ() + "_" + dim
}

function isWallSign(block) {
  let blockId = block.getId()
  return blockId.indexOf("wall_sign") !== -1
}

function isChest(block) {
  let blockId = block.getId()
  return blockId.indexOf("chest") !== -1 && blockId.indexOf("ender_chest") === -1
}

function getAttachedBlock(signBlock) {
  let stateStr = signBlock.getBlockState().toString()
  let facing = null

  let facingStart = stateStr.indexOf("facing=")
  if (facingStart !== -1) {
    let facingEnd = stateStr.indexOf(",", facingStart)
    if (facingEnd === -1) {
      facingEnd = stateStr.indexOf("]", facingStart)
    }
    facing = stateStr.substring(facingStart + 7, facingEnd)
  }

  if (facing === "east") return signBlock.getWest()
  if (facing === "west") return signBlock.getEast()
  if (facing === "north") return signBlock.getSouth()
  if (facing === "south") return signBlock.getNorth()
  return null
}

// Extract only digits from a string (Rhino doesn't support regex in replace)
function extractDigits(str) {
  let result = ""
  for (let i = 0; i < str.length; i++) {
    let c = str.charAt(i)
    if (c >= "0" && c <= "9") {
      result += c
    }
  }
  return result
}

// Remove surrounding quotes from sign text (stored as JSON strings)
// Also extracts "text" field from JSON text components
function unquoteSignText(str) {
  // Try parsing as JSON - sign text is stored as JSON string literals or components
  try {
    let parsed = JSON.parse(str)
    // If it's a simple string, return it
    if (typeof parsed === "string") {
      return parsed
    }
    // If it's a text component object with "text" field, extract it
    if (typeof parsed === "object" && parsed !== null && parsed.text) {
      return parsed.text
    }
  } catch (e) {
    // ignore parse errors
  }

  // Fallback: manual quote removal
  if (str.length >= 2 && str.charCodeAt(0) === 34 && str.charCodeAt(str.length - 1) === 34) {
    return str.substring(1, str.length - 1)
  }

  return str
}

// ============================================================================
// SIGN TEXT PARSING
// ============================================================================

function parseSignText(signBlock) {
  let nbt = signBlock.getEntityData()
  if (!nbt) {
    console.warn("[KubeShop] No entity data on sign")
    return null
  }

  let frontText = nbt.getCompound("front_text")
  if (!frontText) {
    console.warn("[KubeShop] No front_text in sign NBT")
    return null
  }

  let messages = frontText.getList("messages", 8)
  if (!messages || messages.size() < 4) {
    console.warn("[KubeShop] Invalid messages in sign NBT")
    return null
  }

  let line1 = unquoteSignText(messages.getString(0))
  let shopType = null

  let line1Upper = line1.toUpperCase()
  if (line1Upper.indexOf("[BUY]") !== -1) {
    shopType = "BUY"
  } else if (line1Upper.indexOf("[SELL]") !== -1) {
    shopType = "SELL"
  }

  if (!shopType) {
    console.warn("[KubeShop] No [BUY] or [SELL] found on sign")
    return null
  }

  let line4 = unquoteSignText(messages.getString(3))
  let priceStr = extractDigits(line4)
  let price = parseInt(priceStr)

  if (isNaN(price) || price < 0) {
    console.warn("[KubeShop] Invalid price on sign")
    return null
  }

  return { type: shopType, price: price }
}

function updateSignForShop(signBlock, shopType, price) {
  let nbt = signBlock.getEntityData()
  if (!nbt) return

  let frontText = nbt.getCompound("front_text")
  if (!frontText) return

  let messages = frontText.getList("messages", 8)
  if (!messages || messages.size() < 4) return

  // Preserve existing description lines (indices 1 and 2)
  let line2Original = messages.getString(1)
  let line3Original = messages.getString(2)

  // Format: price with $ at end (e.g., "10$")
  let line1Component = '{"text":"[' + shopType + ']","color":"yellow"}'
  let line4Component = '{"text":"' + price + '$","color":"green"}'

  // Create a new messages list to ensure proper NBT handling
  let newMessages = NBT.listTag()
  newMessages.add(NBT.stringTag(line1Component))
  newMessages.add(NBT.stringTag(line2Original))
  newMessages.add(NBT.stringTag(line3Original))
  newMessages.add(NBT.stringTag(line4Component))

  frontText.put("messages", newMessages)
  nbt.put("front_text", frontText)

  // Wax the sign to prevent text editing
  nbt.putByte("is_waxed", 1)

  // Update using setEntityData and force sync
  signBlock.setEntityData(nbt)

  // Force block update to sync to client
  let level = signBlock.getLevel()
  let pos = signBlock.getPos()
  let state = signBlock.getBlockState()
  level.sendBlockUpdated(pos, state, state, 3)
}

// ============================================================================
// INVENTORY HELPERS
// ============================================================================

function serializeInventory(chestBlock) {
  let inv = chestBlock.getInventory()
  if (!inv) return "[]"

  let items = []
  // Try different methods to get slot count
  let slots = inv.getSlots ? inv.getSlots() : (inv.size ? inv.size() : 27)

  for (let i = 0; i < slots; i++) {
    // Try different methods to get item in slot
    let stack = null
    if (inv.getStackInSlot) {
      stack = inv.getStackInSlot(i)
    } else if (inv.getItem) {
      stack = inv.getItem(i)
    }

    if (stack && !stack.isEmpty()) {
      items.push({
        id: stack.getId(),
        count: stack.getCount(),
        nbt: stack.hasNBT && stack.hasNBT() ? stack.getNbt().toString() : null
      })
    }
  }

  return JSON.stringify(items)
}

function chestHasItems(chestBlock, itemTemplateJson) {
  let missing = getMissingItems(chestBlock.getInventory(), itemTemplateJson)
  return missing.length === 0
}

// Returns array of missing item IDs (simplified names)
function getMissingItems(inv, itemTemplateJson) {
  let template = JSON.parse(itemTemplateJson)
  if (!inv) return template.map(function(item) { return item.id })

  let needed = {}
  for (let i = 0; i < template.length; i++) {
    let item = template[i]
    let key = item.id
    needed[key] = (needed[key] || 0) + item.count
  }

  let slots = inv.getSlots ? inv.getSlots() : (inv.size ? inv.size() : 27)
  for (let i = 0; i < slots; i++) {
    let stack = inv.getStackInSlot ? inv.getStackInSlot(i) : inv.getItem(i)
    if (stack && !stack.isEmpty()) {
      let key = stack.getId()
      if (needed[key]) {
        needed[key] -= stack.getCount()
      }
    }
  }

  let missing = []
  for (let key in needed) {
    if (needed[key] > 0) {
      // Simplify item name: "minecraft:diamond_sword" -> "Diamond Sword"
      let simpleName = key.replace("minecraft:", "").replace(/_/g, " ")
      // Capitalize words
      simpleName = simpleName.split(" ").map(function(word) {
        return word.charAt(0).toUpperCase() + word.slice(1)
      }).join(" ")
      missing.push(needed[key] + "x " + simpleName)
    }
  }
  return missing
}

function removeItemsFromChest(chestBlock, itemTemplateJson) {
  let template = JSON.parse(itemTemplateJson)
  let inv = chestBlock.getInventory()
  if (!inv) return false

  let toRemove = {}
  for (let i = 0; i < template.length; i++) {
    let item = template[i]
    let key = item.id
    toRemove[key] = (toRemove[key] || 0) + item.count
  }

  let slots = inv.getSlots ? inv.getSlots() : (inv.size ? inv.size() : 27)
  for (let i = 0; i < slots; i++) {
    let stack = inv.getStackInSlot ? inv.getStackInSlot(i) : inv.getItem(i)
    if (stack && !stack.isEmpty()) {
      let key = stack.getId()
      if (toRemove[key] && toRemove[key] > 0) {
        let removeCount = Math.min(toRemove[key], stack.getCount())
        // Try extractItem or shrink the stack directly
        if (inv.extractItem) {
          inv.extractItem(i, removeCount, false)
        } else {
          stack.shrink(removeCount)
        }
        toRemove[key] -= removeCount
      }
    }
  }

  return true
}

function playerHasItems(player, itemTemplateJson) {
  return getMissingPlayerItems(player, itemTemplateJson).length === 0
}

// Returns array of missing items from player inventory (with amounts)
function getMissingPlayerItems(player, itemTemplateJson) {
  let template = JSON.parse(itemTemplateJson)
  let inv = player.getInventory()

  let needed = {}
  for (let i = 0; i < template.length; i++) {
    let item = template[i]
    let key = item.id
    needed[key] = (needed[key] || 0) + item.count
  }

  let slots = inv.getSlots ? inv.getSlots() : (inv.size ? inv.size() : 36)
  for (let i = 0; i < slots; i++) {
    let stack = inv.getStackInSlot ? inv.getStackInSlot(i) : inv.getItem(i)
    if (stack && !stack.isEmpty()) {
      let key = stack.getId()
      if (needed[key]) {
        needed[key] -= stack.getCount()
      }
    }
  }

  let missing = []
  for (let key in needed) {
    if (needed[key] > 0) {
      let simpleName = key.replace("minecraft:", "").replace(/_/g, " ")
      simpleName = simpleName.split(" ").map(function(word) {
        return word.charAt(0).toUpperCase() + word.slice(1)
      }).join(" ")
      missing.push(needed[key] + "x " + simpleName)
    }
  }
  return missing
}

function removeItemsFromPlayer(player, itemTemplateJson) {
  let template = JSON.parse(itemTemplateJson)
  let inv = player.getInventory()

  let toRemove = {}
  for (let i = 0; i < template.length; i++) {
    let item = template[i]
    let key = item.id
    toRemove[key] = (toRemove[key] || 0) + item.count
  }

  let slots = inv.getSlots ? inv.getSlots() : (inv.size ? inv.size() : 36)
  for (let i = 0; i < slots; i++) {
    let stack = inv.getStackInSlot ? inv.getStackInSlot(i) : inv.getItem(i)
    if (stack && !stack.isEmpty()) {
      let key = stack.getId()
      if (toRemove[key] && toRemove[key] > 0) {
        let removeCount = Math.min(toRemove[key], stack.getCount())
        if (inv.extractItem) {
          inv.extractItem(i, removeCount, false)
        } else {
          stack.shrink(removeCount)
        }
        toRemove[key] -= removeCount
      }
    }
  }

  return true
}

function giveItemsToPlayer(player, itemTemplateJson) {
  let template = JSON.parse(itemTemplateJson)

  for (let i = 0; i < template.length; i++) {
    let item = template[i]
    player.give(Item.of(item.id, item.count))
  }
}

function addItemsToChest(chestBlock, itemTemplateJson) {
  let template = JSON.parse(itemTemplateJson)
  let inv = chestBlock.getInventory()
  if (!inv) return false

  for (let i = 0; i < template.length; i++) {
    let item = template[i]
    let stack = Item.of(item.id, item.count)
    if (inv.insertItem) {
      let remaining = inv.insertItem(stack, false)
      if (remaining && !remaining.isEmpty()) {
        return false
      }
    } else {
      // Fallback: find empty slot or matching stack
      let inserted = false
      let slots = inv.getSlots ? inv.getSlots() : (inv.size ? inv.size() : 27)
      for (let s = 0; s < slots && !inserted; s++) {
        let existing = inv.getStackInSlot ? inv.getStackInSlot(s) : inv.getItem(s)
        if (!existing || existing.isEmpty()) {
          if (inv.setItem) inv.setItem(s, stack)
          inserted = true
        }
      }
      if (!inserted) return false
    }
  }

  return true
}

function chestHasSpace(chestBlock, itemTemplateJson) {
  let template = JSON.parse(itemTemplateJson)
  let inv = chestBlock.getInventory()
  if (!inv) return false

  // Simple check: count empty slots vs items needed
  let emptySlots = 0
  let slots = inv.getSlots ? inv.getSlots() : (inv.size ? inv.size() : 27)
  for (let i = 0; i < slots; i++) {
    let stack = inv.getStackInSlot ? inv.getStackInSlot(i) : inv.getItem(i)
    if (!stack || stack.isEmpty()) {
      emptySlots++
    }
  }

  return emptySlots >= template.length
}

// ============================================================================
// EVENT HANDLERS
// ============================================================================

// Try to load FTB Chunks API for protection bypass on shop signs
let FTBChunksAPI = null
let ftbChunksAvailable = false

try {
  FTBChunksAPI = Java.loadClass('dev.ftb.mods.ftbchunks.api.FTBChunksAPI')
  ftbChunksAvailable = true
  console.info("[KubeShop] FTB Chunks API loaded")
} catch(e) {
  console.info("[KubeShop] FTB Chunks API not available (FTB Chunks not installed?): " + e)
}

// Track which players currently have bypass enabled (for cleanup)
// This is persisted to server NBT so we can clean up after /reload
let playersWithBypass = {}
let needsBypassCleanup = true  // Always check on script load

// Load bypass tracking from server persistent data
function loadBypassData(server) {
  try {
    let rootNbt = getRootNbt(server)
    if (rootNbt.contains(BYPASS_KEY)) {
      let bypassNbt = rootNbt.getCompound(BYPASS_KEY)
      let keys = bypassNbt.getAllKeys().toArray()
      let result = {}
      for (let i = 0; i < keys.length; i++) {
        let uuid = keys[i]
        result[uuid] = bypassNbt.getString(uuid)  // Username
      }
      return result
    }
  } catch(e) {
    console.warn("[KubeShop] Could not load bypass data: " + e)
  }
  return {}
}

// Save bypass tracking to server persistent data
function saveBypassData(server) {
  try {
    let rootNbt = getRootNbt(server)
    let bypassNbt = NBT.compoundTag()
    for (let uuid in playersWithBypass) {
      bypassNbt.putString(uuid, playersWithBypass[uuid])
    }
    rootNbt.put(BYPASS_KEY, bypassNbt)
  } catch(e) {
    console.warn("[KubeShop] Could not save bypass data: " + e)
  }
}

// Get FTB Chunks manager safely
function getFTBChunksManager() {
  if (!ftbChunksAvailable || !FTBChunksAPI) return null
  try {
    let api = FTBChunksAPI.api()
    if (api && api.isManagerLoaded()) {
      return api.getManager()
    }
  } catch(e) {
    // Manager not ready yet
  }
  return null
}

// Get proper Java UUID from player
function getPlayerUUID(player) {
  // Try different methods to get the UUID
  try {
    // Method 1: getUUID() - standard Minecraft
    if (player.getUUID) return player.getUUID()
  } catch(e) {}

  try {
    // Method 2: uuid property (KubeJS wrapper)
    if (player.uuid) return player.uuid
  } catch(e) {}

  try {
    // Method 3: Parse from string UUID using Java
    let uuidStr = player.getStringUuid()
    let UUID = Java.loadClass('java.util.UUID')
    return UUID.fromString(uuidStr)
  } catch(e) {}

  return null
}

// Enable bypass for a player (with tracking)
function enableShopBypass(player) {
  let manager = getFTBChunksManager()
  if (!manager) return false

  let uuid = getPlayerUUID(player)
  let uuidStr = player.getStringUuid()

  if (!uuid) return false

  // Don't enable if already has bypass (e.g. admin)
  if (manager.getBypassProtection(uuid)) return false

  manager.setBypassProtection(uuid, true)
  playersWithBypass[uuidStr] = player.getName().getString()  // Store username for logging
  saveBypassData(player.getServer())  // Persist to NBT for reload safety

  return manager.getBypassProtection(uuid)
}

// Disable bypass for a player (with tracking)
function disableShopBypass(player) {
  let manager = getFTBChunksManager()
  if (!manager) return

  let uuid = getPlayerUUID(player)
  let uuidStr = player.getStringUuid()

  // Only disable if we enabled it
  if (playersWithBypass[uuidStr] && uuid) {
    manager.setBypassProtection(uuid, false)
    delete playersWithBypass[uuidStr]
    saveBypassData(player.getServer())  // Persist to NBT for reload safety
  }
}

// Check if sign is waxed
function isSignWaxed(block) {
  try {
    let nbt = block.getEntityData()
    if (!nbt) return false
    return nbt.getByte("is_waxed") === 1
  } catch(e) {
    return false
  }
}

// Check if player is looking at a valid shop sign (must be waxed)
function getShopSignPlayerIsLookingAt(player) {
  try {
    // Raycast 5 blocks max - KubeJS returns KubeRayTraceResult
    let hitResult = player.rayTrace(5, false)
    if (!hitResult) return null

    // KubeJS rayTrace returns object with .block property if hit a block
    let block = hitResult.block
    if (!block) return null

    // Must be a sign
    let blockId = block.getId()
    if (!blockId.includes('sign')) return null

    // Must be waxed (non-waxed signs open text editor)
    if (!isSignWaxed(block)) return null

    // Must be a registered shop
    let signKey = getBlockKey(block)
    let shop = shopsCache[signKey]

    if (!shop) return null

    return { block: block, signKey: signKey, shop: shop }
  } catch(e) {
    return null
  }
}

// Server tick - manage bypass protection for players looking at shop signs
ServerEvents.tick(event => {
  // Handle delayed bypass cleanup after reload
  // We load from server NBT to know who had bypass enabled before reload
  if (needsBypassCleanup) {
    let manager = getFTBChunksManager()
    if (manager) {
      needsBypassCleanup = false  // Clear flag first to prevent repeated attempts

      // Load bypass data from server persistent data
      playersWithBypass = loadBypassData(event.server)

      if (Object.keys(playersWithBypass).length > 0) {
        // Log who had bypass
        let uuids = Object.keys(playersWithBypass)
        console.info("[KubeShop] Found " + uuids.length + " player(s) with bypass leftover, cleaning up:")
        for (let i = 0; i < uuids.length; i++) {
          let uuidStr = uuids[i]
          let name = playersWithBypass[uuidStr] || "Unknown"
          console.info("[KubeShop]   - " + name + " (" + uuidStr + ")")
        }

        // Disable bypass for each
        let cleanedUp = 0
        for (let uuidStr in playersWithBypass) {
          try {
            let UUID = Java.loadClass('java.util.UUID')
            let uuid = UUID.fromString(uuidStr)
            if (manager.getBypassProtection(uuid)) {
              manager.setBypassProtection(uuid, false)
              cleanedUp++
            }
          } catch(e) {
            console.warn("[KubeShop] Failed to disable bypass for " + uuidStr + ": " + e)
          }
        }

        // Clear the tracking and save empty NBT
        playersWithBypass = {}
        saveBypassData(event.server)

        if (cleanedUp > 0) {
          console.info("[KubeShop] Disabled bypass for " + cleanedUp + " player(s) on reload")
        }
      }
    }
    // If manager still not available, flag stays true and we retry next tick
  }

  // Only check every 2 ticks for responsiveness
  if (event.server.getTickCount() % 2 !== 0) return

  // Skip if FTB Chunks not available
  if (!ftbChunksAvailable) return

  ensureDataLoaded(event.server)

  // Process all online players
  event.server.getPlayers().forEach(player => {
    let uuidStr = player.getStringUuid()
    let hasCurrentBypass = playersWithBypass[uuidStr] || false

    // Check if player should have bypass (looking at waxed shop sign)
    let shopInfo = getShopSignPlayerIsLookingAt(player)
    let shouldHaveBypass = (shopInfo !== null)

    // Update bypass state if changed
    if (shouldHaveBypass && !hasCurrentBypass) {
      // Enable bypass - player is now looking at a shop sign
      enableShopBypass(player)
    } else if (!shouldHaveBypass && hasCurrentBypass) {
      // Disable bypass - player is no longer looking at a shop sign
      disableShopBypass(player)
    }
  })

  // Safety: Clean up bypass for any offline players (in case of disconnect)
  for (let uuidStr in playersWithBypass) {
    let stillOnline = false
    event.server.getPlayers().forEach(p => {
      if (p.getStringUuid() === uuidStr) stillOnline = true
    })
    if (!stillOnline) {
      // Player disconnected, clean up
      delete playersWithBypass[uuidStr]
    }
  }
})

// Load all data on server start
ServerEvents.loaded(event => {
  dataLoaded = false  // Reset flag so data reloads

  // Clear in-memory caches to force fresh load from persistent data
  balancesCache = {}
  shopsCache = {}
  historyCache = {}
  playersWithBypass = {}
  ensureDataLoaded(event.server)
  console.info("[KubeShop] Loaded " + Object.keys(shopsCache).length + " shops")

  // Initialize balances for all known players from profile cache
  try {
    let profileCache = event.server.getProfileCache()
    if (profileCache) {
      let initializedCount = 0
      // Get all cached profiles using the load method
      // load() returns Stream<GameProfileInfo>, where GameProfileInfo wraps GameProfile
      let profiles = profileCache.load()
      if (profiles && profiles.iterator) {
        let iterator = profiles.iterator()
        while (iterator.hasNext()) {
          let profileInfo = iterator.next()
          // GameProfileInfo has getProfile() method to get the actual GameProfile
          let profile = profileInfo.getProfile ? profileInfo.getProfile() : profileInfo
          let uuid = profile.getId().toString()
          if (balancesCache[uuid] === undefined) {
            balancesCache[uuid] = STARTING_BALANCE
            saveBalance(event.server, uuid)
            initializedCount++
          }
        }
        if (initializedCount > 0) {
          console.info("[KubeShop] Initialized balances for " + initializedCount + " new players")
        }
      }
    }
  } catch(e) {
    console.warn("[KubeShop] Could not initialize all player balances: " + e)
  }
})

// Clean up bypass when player disconnects
PlayerEvents.loggedOut(event => {
  let player = event.player
  let uuidStr = player.getStringUuid()

  if (playersWithBypass[uuidStr]) {
    disableShopBypass(player)
  }
})

// Handle block breaking - cleanup shops and ownership
BlockEvents.broken(event => {
  ensureDataLoaded(event.server)
  let blockKey = getBlockKey(event.block)
  let player = event.getEntity()

  if (isWallSign(event.block)) {
    let shop = getShop(blockKey)
    if (shop) {
      removeShop(event.server, blockKey)
      console.info("[KubeShop] Shop removed (sign broken)")
      if (player) {
        player.sendSystemMessage(Component.gold("Shop removed!"))
      }
    }
  }

  if (isChest(event.block)) {
    for (let signKey in shopsCache) {
      if (shopsCache[signKey].chestPos === blockKey) {
        removeShop(event.server, signKey)
        console.info("[KubeShop] Shop removed (chest broken)")
        if (player) {
          player.sendSystemMessage(Component.gold("Shop removed (chest destroyed)!"))
        }
      }
    }
  }
})

// Main shop interaction handler
BlockEvents.rightClicked(event => {
  if (!isWallSign(event.block)) return

  let player = event.getEntity()
  let server = event.block.getLevel().getServer()

  // Ensure data is loaded (handles /reload)
  ensureDataLoaded(server)

  let signKey = getBlockKey(event.block)
  let existingShop = getShop(signKey)
  let isCrouching = player.isCrouching()

  if (isCrouching) {
    // SHOP CREATION only (removal is done by breaking sign/chest)
    if (existingShop) {
      // Shop already exists, show shop info on shift-click
      let infoTemplate = JSON.parse(existingShop.itemTemplate)
      let infoItemNames = []
      for (let i = 0; i < infoTemplate.length; i++) {
        let itemId = infoTemplate[i].id
        let count = infoTemplate[i].count
        let simpleName = itemId.replace("minecraft:", "").replace(/_/g, " ")
        simpleName = simpleName.split(" ").map(function(word) {
          return word.charAt(0).toUpperCase() + word.slice(1)
        }).join(" ")
        infoItemNames.push(count + "x " + simpleName)
      }
      let infoItemsStr = infoItemNames.join(", ")

      // BUY = shop selling to users, SELL = shop buying from users
      let actionText = existingShop.type === "BUY" ? "selling" : "buying"

      player.sendSystemMessage(
        Component.empty()
          .append(Component.gold("Shop is " + actionText + " "))
          .append(Component.white(infoItemsStr))
          .append(Component.gold(" for "))
          .append(Component.green(existingShop.price + "$"))
      )
      event.cancel()
      return
    }

    let signData = parseSignText(event.block)
    if (!signData) return

    let attachedBlock = getAttachedBlock(event.block)
    if (!attachedBlock || !isChest(attachedBlock)) {
      player.sendSystemMessage(Component.red("Sign must be placed on a chest"))
      event.cancel()
      return
    }

    let chestKey = getBlockKey(attachedBlock)

    let itemTemplate = serializeInventory(attachedBlock)
    if (itemTemplate === "[]") {
      player.sendSystemMessage(Component.red("Put items in chest first"))
      event.cancel()
      return
    }

    let shopData = {
      owner: player.getStringUuid(),
      chestPos: chestKey,
      type: signData.type,
      price: signData.price,
      itemTemplate: itemTemplate
    }

    saveShop(server, signKey, shopData)
    updateSignForShop(event.block, signData.type, signData.price)

    // Build item list for message
    let template = JSON.parse(itemTemplate)
    let itemNames = []
    for (let i = 0; i < template.length; i++) {
      let itemId = template[i].id
      let count = template[i].count
      // Simplify: "minecraft:diamond_sword" -> "Diamond Sword"
      let simpleName = itemId.replace("minecraft:", "").replace(/_/g, " ")
      simpleName = simpleName.split(" ").map(function(word) {
        return word.charAt(0).toUpperCase() + word.slice(1)
      }).join(" ")
      itemNames.push(count + "x " + simpleName)
    }
    let itemsStr = itemNames.join(", ")

    // BUY = shop selling to users, SELL = shop buying from users
    let actionText = signData.type === "BUY" ? "selling to users" : "buying from users"

    let msg = Component.empty()
      .append(Component.gold("Shop created! Shop is " + actionText + " "))
      .append(Component.white(itemsStr))
      .append(Component.gold(" for "))
      .append(Component.green(signData.price + "$"))

    player.sendSystemMessage(msg)
    event.cancel()
    return
  }

  // SHOP USAGE (not crouching)
  if (!existingShop) return

  // Only waxed signs are valid shops (prevents interaction with non-finalized shops)
  if (!isSignWaxed(event.block)) return

  let chestPosStr = existingShop.chestPos
  let posParts = chestPosStr.split("_")
  let chestX = parseInt(posParts[0])
  let chestY = parseInt(posParts[1])
  let chestZ = parseInt(posParts[2])

  let level = event.block.getLevel()
  let chestBlock = level.getBlock(chestX, chestY, chestZ)

  if (!chestBlock || !isChest(chestBlock)) {
    player.sendSystemMessage(Component.red("Shop chest not found"))
    return
  }

  let buyerUuid = player.getStringUuid()
  let ownerUuid = existingShop.owner
  let price = existingShop.price
  let itemTemplate = existingShop.itemTemplate

  if (existingShop.type === "BUY") {
    if (!hasBalance(server, buyerUuid, price)) {
      let buyerBal = getBalance(server, buyerUuid)
      let msg = Component.empty()
        .append(Component.red("You need "))
        .append(Component.yellow("$" + price))
        .append(Component.red(" but only have "))
        .append(Component.yellow("$" + buyerBal))
      player.sendSystemMessage(msg)
      event.cancel()
      return
    }

    let missingItems = getMissingItems(chestBlock.getInventory(), itemTemplate)
    if (missingItems.length > 0) {
      player.sendSystemMessage(Component.red("Shop is out of stock"))

      // Notify owner if online
      let ownerPlayer = server.getPlayer(ownerUuid)
      if (ownerPlayer) {
        let missingStr = missingItems.join(", ")
        ownerPlayer.sendSystemMessage(
          Component.empty()
            .append(Component.yellow(player.getName().getString()))
            .append(Component.red(" tried to buy from your shop but you're out of: "))
            .append(Component.white(missingStr))
        )
      }

      event.cancel()
      return
    }

    removeItemsFromChest(chestBlock, itemTemplate)
    removeBalance(server, buyerUuid, price)
    giveItemsToPlayer(player, itemTemplate)
    addBalance(server, ownerUuid, price)

    // Build item names for message
    let template = JSON.parse(itemTemplate)
    let itemNames = []
    for (let i = 0; i < template.length; i++) {
      let itemId = template[i].id
      let count = template[i].count
      let simpleName = itemId.replace("minecraft:", "").replace(/_/g, " ")
      simpleName = simpleName.split(" ").map(function(word) {
        return word.charAt(0).toUpperCase() + word.slice(1)
      }).join(" ")
      itemNames.push(count + "x " + simpleName)
    }
    let itemsStr = itemNames.join(", ")

    // Get owner name for history
    let ownerName = "Unknown"
    let ownerPlayer = server.getPlayer(ownerUuid)
    if (ownerPlayer) {
      ownerName = ownerPlayer.getName().getString()
    }

    // Record history for buyer and shop owner
    addHistoryEntry(server, buyerUuid, "shop_buy", price, ownerName, itemsStr)
    addHistoryEntry(server, ownerUuid, "shop_sell", price, player.getName().getString(), itemsStr)

    player.sendSystemMessage(
      Component.empty()
        .append(Component.gold("Purchased "))
        .append(Component.white(itemsStr))
        .append(Component.gold(" for "))
        .append(Component.green(price + "$"))
    )

    if (ownerPlayer) {
      ownerPlayer.sendSystemMessage(
        Component.empty()
          .append(Component.yellow(player.getName().getString()))
          .append(Component.gold(" bought "))
          .append(Component.white(itemsStr))
          .append(Component.gold(" from your shop for "))
          .append(Component.green(price + "$"))
      )
    }

  } else {
    // SELL shop
    let missingPlayerItems = getMissingPlayerItems(player, itemTemplate)
    if (missingPlayerItems.length > 0) {
      let missingPlayerStr = missingPlayerItems.join(", ")
      player.sendSystemMessage(
        Component.empty()
          .append(Component.red("You're missing: "))
          .append(Component.white(missingPlayerStr))
      )
      event.cancel()
      return
    }

    if (!hasBalance(server, ownerUuid, price)) {
      player.sendSystemMessage(Component.red("Shop owner cannot afford this purchase"))

      // Notify owner if online
      let ownerPlayerBroke = server.getPlayer(ownerUuid)
      if (ownerPlayerBroke) {
        let brokeTemplate = JSON.parse(itemTemplate)
        let brokeItemNames = []
        for (let i = 0; i < brokeTemplate.length; i++) {
          let itemId = brokeTemplate[i].id
          let count = brokeTemplate[i].count
          let simpleName = itemId.replace("minecraft:", "").replace(/_/g, " ")
          simpleName = simpleName.split(" ").map(function(word) {
            return word.charAt(0).toUpperCase() + word.slice(1)
          }).join(" ")
          brokeItemNames.push(count + "x " + simpleName)
        }
        let brokeItemsStr = brokeItemNames.join(", ")
        ownerPlayerBroke.sendSystemMessage(
          Component.empty()
            .append(Component.yellow(player.getName().getString()))
            .append(Component.red(" tried to sell "))
            .append(Component.white(brokeItemsStr))
            .append(Component.red(" but you can't afford "))
            .append(Component.yellow(price + "$"))
        )
      }

      event.cancel()
      return
    }

    if (!chestHasSpace(chestBlock, itemTemplate)) {
      player.sendSystemMessage(Component.red("Shop chest is full"))

      // Notify owner if online
      let ownerPlayerFull = server.getPlayer(ownerUuid)
      if (ownerPlayerFull) {
        let fullTemplate = JSON.parse(itemTemplate)
        let fullItemNames = []
        for (let i = 0; i < fullTemplate.length; i++) {
          let itemId = fullTemplate[i].id
          let count = fullTemplate[i].count
          let simpleName = itemId.replace("minecraft:", "").replace(/_/g, " ")
          simpleName = simpleName.split(" ").map(function(word) {
            return word.charAt(0).toUpperCase() + word.slice(1)
          }).join(" ")
          fullItemNames.push(count + "x " + simpleName)
        }
        let fullItemsStr = fullItemNames.join(", ")
        ownerPlayerFull.sendSystemMessage(
          Component.empty()
            .append(Component.yellow(player.getName().getString()))
            .append(Component.red(" tried to sell "))
            .append(Component.white(fullItemsStr))
            .append(Component.red(" but your shop chest is full"))
        )
      }

      event.cancel()
      return
    }

    removeItemsFromPlayer(player, itemTemplate)
    addItemsToChest(chestBlock, itemTemplate)
    removeBalance(server, ownerUuid, price)
    addBalance(server, buyerUuid, price)

    // Build item names for message
    let sellTemplate = JSON.parse(itemTemplate)
    let sellItemNames = []
    for (let i = 0; i < sellTemplate.length; i++) {
      let itemId = sellTemplate[i].id
      let count = sellTemplate[i].count
      let simpleName = itemId.replace("minecraft:", "").replace(/_/g, " ")
      simpleName = simpleName.split(" ").map(function(word) {
        return word.charAt(0).toUpperCase() + word.slice(1)
      }).join(" ")
      sellItemNames.push(count + "x " + simpleName)
    }
    let sellItemsStr = sellItemNames.join(", ")

    // Get owner name for history
    let sellOwnerName = "Unknown"
    let ownerPlayer = server.getPlayer(ownerUuid)
    if (ownerPlayer) {
      sellOwnerName = ownerPlayer.getName().getString()
    }

    // Record history for seller (player) and shop owner
    // For SELL shop: player sells items TO shop, receives money
    addHistoryEntry(server, buyerUuid, "shop_sell", price, sellOwnerName, sellItemsStr)
    addHistoryEntry(server, ownerUuid, "shop_buy", price, player.getName().getString(), sellItemsStr)

    player.sendSystemMessage(
      Component.empty()
        .append(Component.gold("Sold "))
        .append(Component.white(sellItemsStr))
        .append(Component.gold(" for "))
        .append(Component.green(price + "$"))
    )

    if (ownerPlayer) {
      ownerPlayer.sendSystemMessage(
        Component.empty()
          .append(Component.yellow(player.getName().getString()))
          .append(Component.gold(" sold "))
          .append(Component.white(sellItemsStr))
          .append(Component.gold(" to your shop for "))
          .append(Component.green(price + "$"))
      )
    }
  }

  event.cancel()
})

// ============================================================================
// COMMANDS
// ============================================================================

ServerEvents.commandRegistry(event => {
  let Commands = event.getCommands()
  let Arguments = event.getArguments()

  // /wallet - Main command with subcommands
  event.register(
    Commands.literal("wallet")
      // /wallet (no args) - show help
      .executes(ctx => {
        let src = ctx.getSource()
        src.sendSystemMessage(Component.gold("=== Wallet Commands ==="))
        src.sendSystemMessage(Component.yellow("/wallet balance").append(Component.gray(" - Check your balance")))
        src.sendSystemMessage(Component.yellow("/wallet pay <player> <amount>").append(Component.gray(" - Send money")))
        src.sendSystemMessage(Component.yellow("/wallet withdraw <amount>").append(Component.gray(" - Withdraw as coins (auto-split)")))
        src.sendSystemMessage(Component.yellow("/wallet withdraw <amount> <denom>").append(Component.gray(" - Withdraw as specific coin (1/10/100/1000)")))
        src.sendSystemMessage(Component.yellow("/wallet deposit").append(Component.gray(" - Deposit all coins")))
        src.sendSystemMessage(Component.yellow("/wallet deposit <amount>").append(Component.gray(" - Deposit specific value")))
        src.sendSystemMessage(Component.yellow("/wallet top").append(Component.gray(" - Richest players leaderboard")))
        src.sendSystemMessage(Component.yellow("/wallet history").append(Component.gray(" - Transaction history")))
        src.sendSystemMessage(Component.yellow("/wallet shop help").append(Component.gray(" - Shop creation guide")))
        if (src.hasPermission(2)) {
          src.sendSystemMessage(Component.red("/wallet admin").append(Component.gray(" - Admin commands")))
        }
        return 1
      })

      // /wallet balance - Check your own balance
      .then(Commands.literal("balance")
        .executes(ctx => {
          let player = ctx.getSource().getPlayer()
          if (player == null) {
            ctx.getSource().sendFailure(Component.red("This command can only be used by players"))
            return 0
          }

          let srv = ctx.getSource().getServer()
          let pUuid = player.getStringUuid()
          let bal = getBalance(srv, pUuid)

          player.sendSystemMessage(
            Component.empty()
              .append(Component.gold("Your balance: "))
              .append(Component.green(formatBalance(bal)))
          )

          return 1
        })
      )

      // /wallet help - Show help
      .then(Commands.literal("help")
        .executes(ctx => {
          let src = ctx.getSource()
          src.sendSystemMessage(Component.gold("=== Wallet Commands ==="))
          src.sendSystemMessage(Component.yellow("/wallet balance").append(Component.gray(" - Check your balance")))
          src.sendSystemMessage(Component.yellow("/wallet pay <player> <amount>").append(Component.gray(" - Send money")))
          src.sendSystemMessage(Component.gold("--- Coin Commands ---"))
          src.sendSystemMessage(Component.yellow("/wallet withdraw <amount>").append(Component.gray(" - Withdraw as coins (auto-split)")))
          src.sendSystemMessage(Component.yellow("/wallet withdraw <amount> <denom>").append(Component.gray(" - Withdraw as specific coin")))
          src.sendSystemMessage(Component.gray("  Denominations: 1, 10, 100, 1000, 10000"))
          src.sendSystemMessage(Component.gray("  Example: /wallet withdraw 100 10 = 10x $10 coins"))
          src.sendSystemMessage(Component.yellow("/wallet deposit").append(Component.gray(" - Deposit all coins in inventory")))
          src.sendSystemMessage(Component.yellow("/wallet deposit <amount>").append(Component.gray(" - Deposit specific value from coins")))
          src.sendSystemMessage(Component.gold("--- Other ---"))
          src.sendSystemMessage(Component.yellow("/wallet top").append(Component.gray(" - Richest players leaderboard")))
          src.sendSystemMessage(Component.yellow("/wallet history").append(Component.gray(" - Transaction history")))
          src.sendSystemMessage(Component.yellow("/wallet shop help").append(Component.gray(" - Shop creation guide")))
          if (src.hasPermission(2)) {
            src.sendSystemMessage(Component.red("/wallet admin").append(Component.gray(" - Admin commands")))
          }
          return 1
        })
      )

      // /wallet shop - Shop subcommands
      .then(Commands.literal("shop")
        // /wallet shop (no args) - show shop help
        .executes(ctx => {
          let src = ctx.getSource()
          src.sendSystemMessage(Component.gold("=== Shop Commands ==="))
          src.sendSystemMessage(Component.yellow("/wallet shop help").append(Component.gray(" - Shop creation guide")))
          return 1
        })

        // /wallet shop help - Shop creation guide
        .then(Commands.literal("help")
          .executes(ctx => {
            let src = ctx.getSource()
            src.sendSystemMessage(Component.gold("=== Shop Creation Guide ==="))
            src.sendSystemMessage(Component.white("1. Place a chest with items to sell/buy"))
            src.sendSystemMessage(Component.white("2. Place a wall sign on the chest"))
            src.sendSystemMessage(Component.white("3. Write on the sign:"))
            src.sendSystemMessage(Component.gray("   Line 1: ").append(Component.yellow("[BUY]")).append(Component.gray(" or ")).append(Component.yellow("[SELL]")))
            src.sendSystemMessage(Component.gray("   Line 2-3: Description (optional)"))
            src.sendSystemMessage(Component.gray("   Line 4: Price (e.g. ").append(Component.green("10")).append(Component.gray(")")))
            src.sendSystemMessage(Component.white("4. Shift+right-click the sign to create"))
            src.sendSystemMessage(Component.gold("---"))
            src.sendSystemMessage(Component.yellow("[BUY]").append(Component.gray(" = Players buy FROM the shop")))
            src.sendSystemMessage(Component.yellow("[SELL]").append(Component.gray(" = Players sell TO the shop")))
            src.sendSystemMessage(Component.gray("Right-click shop sign to buy/sell"))
            src.sendSystemMessage(Component.gray("Shift+click existing shop to see info"))
            src.sendSystemMessage(Component.gray("Break sign or chest to remove shop"))
            return 1
          })
        )
      )

      // /wallet pay <player> <amount> - Send money to another player
      .then(Commands.literal("pay")
        .then(
          Commands.argument("recipient", Arguments.GAME_PROFILE.create(event))
            .then(
              Commands.argument("amount", Arguments.INTEGER.create(event))
                .executes(ctx => {
                  let sender = ctx.getSource().getPlayer()
                  if (sender == null) {
                    ctx.getSource().sendFailure(Component.red("This command can only be used by players"))
                    return 0
                  }

                  let payAmount = Arguments.INTEGER.getResult(ctx, "amount")
                  if (payAmount <= 0) {
                    ctx.getSource().sendFailure(Component.red("Amount must be positive"))
                    return 0
                  }

                  let recipientProfiles = Arguments.GAME_PROFILE.getResult(ctx, "recipient")
                  let recipientArray = recipientProfiles.toArray()
                  if (recipientArray.length === 0) {
                    ctx.getSource().sendFailure(Component.red("No player found"))
                    return 0
                  }

                  let payServer = ctx.getSource().getServer()
                  let senderUuid = sender.getStringUuid()
                  let recipientProfile = recipientArray[0]
                  let recipientUuid = recipientProfile.getId().toString()
                  let recipientName = recipientProfile.getName()

                  if (senderUuid === recipientUuid) {
                    ctx.getSource().sendFailure(Component.red("You cannot pay yourself"))
                    return 0
                  }

                  let senderBalance = getBalance(payServer, senderUuid)
                  if (senderBalance < payAmount) {
                    let failMsg = Component.empty()
                      .append(Component.red("Insufficient funds. You have "))
                      .append(Component.yellow(formatBalance(senderBalance)))
                    ctx.getSource().sendFailure(failMsg)
                    return 0
                  }

                  removeBalance(payServer, senderUuid, payAmount)
                  addBalance(payServer, recipientUuid, payAmount)

                  // Record history for both players
                  addHistoryEntry(payServer, senderUuid, "pay_sent", payAmount, recipientName, null)
                  addHistoryEntry(payServer, recipientUuid, "pay_received", payAmount, sender.getName().getString(), null)

                  let successMsg = Component.empty()
                    .append(Component.gold("Sent "))
                    .append(Component.green(formatBalance(payAmount)))
                    .append(Component.gold(" to "))
                    .append(Component.yellow(recipientName))

                  sender.sendSystemMessage(successMsg)

                  let onlineRecipient = payServer.getPlayer(recipientUuid)
                  if (onlineRecipient != null) {
                    let receivedMsg = Component.empty()
                      .append(Component.gold("You received "))
                      .append(Component.green(formatBalance(payAmount)))
                      .append(Component.gold(" from "))
                      .append(Component.yellow(sender.getName().getString()))
                    onlineRecipient.sendSystemMessage(receivedMsg)
                  }

                  return 1
                })
            )
        )
      )

      // /wallet top - Richest players leaderboard
      .then(Commands.literal("top")
        .executes(ctx => {
          let srv = ctx.getSource().getServer()
          ensureDataLoaded(srv)

          // Get all balances and sort by amount
          let entries = []
          for (let uuid in balancesCache) {
            entries.push({ uuid: uuid, balance: balancesCache[uuid] })
          }
          entries.sort(function(a, b) { return b.balance - a.balance })

          // Take top 10
          let top = entries.slice(0, 10)

          ctx.getSource().sendSystemMessage(Component.gold("=== Richest Players ==="))

          if (top.length === 0) {
            ctx.getSource().sendSystemMessage(Component.gray("No players with balances yet"))
            return 1
          }

          for (let i = 0; i < top.length; i++) {
            let entry = top[i]
            let rank = i + 1
            let playerName = "Unknown"

            // Try to get player name from server
            let onlinePlayer = srv.getPlayer(entry.uuid)
            if (onlinePlayer) {
              playerName = onlinePlayer.getName().getString()
            } else {
              // Try to get from game profile cache
              try {
                let profileCache = srv.getProfileCache()
                if (profileCache) {
                  let optProfile = profileCache.get(Java.loadClass('java.util.UUID').fromString(entry.uuid))
                  if (optProfile && optProfile.isPresent()) {
                    playerName = optProfile.get().getName()
                  }
                }
              } catch(e) {
                // Use UUID as fallback
                playerName = entry.uuid.substring(0, 8) + "..."
              }
            }

            let rankColor = rank === 1 ? Component.gold : (rank === 2 ? Component.gray : (rank === 3 ? Component.darkRed : Component.white))
            ctx.getSource().sendSystemMessage(
              Component.empty()
                .append(rankColor("#" + rank + " "))
                .append(Component.yellow(playerName))
                .append(Component.gray(" - "))
                .append(Component.green(formatBalance(entry.balance)))
            )
          }

          return 1
        })
      )

      // /wallet history - Show transaction history
      .then(Commands.literal("history")
        .executes(ctx => {
          let player = ctx.getSource().getPlayer()
          if (player == null) {
            ctx.getSource().sendFailure(Component.red("This command can only be used by players"))
            return 0
          }

          let srv = ctx.getSource().getServer()
          let pUuid = player.getStringUuid()
          let history = getHistory(srv, pUuid)

          ctx.getSource().sendSystemMessage(Component.gold("=== Transaction History ==="))

          if (history.length === 0) {
            ctx.getSource().sendSystemMessage(Component.gray("No transactions yet"))
            return 1
          }

          // Show last 10 transactions
          let toShow = Math.min(history.length, 10)
          for (let i = 0; i < toShow; i++) {
            let entry = history[i]
            let timeStr = formatTimestamp(entry.time)
            let msg = Component.empty().append(Component.gray("[" + timeStr + "] "))

            if (entry.type === "pay_sent") {
              msg.append(Component.red("-" + formatBalance(entry.amount)))
                .append(Component.gray(" sent to "))
                .append(Component.yellow(entry.other))
            } else if (entry.type === "pay_received") {
              msg.append(Component.green("+" + formatBalance(entry.amount)))
                .append(Component.gray(" from "))
                .append(Component.yellow(entry.other))
            } else if (entry.type === "shop_buy") {
              msg.append(Component.red("-" + formatBalance(entry.amount)))
                .append(Component.gray(" bought "))
                .append(Component.white(entry.desc || "items"))
                .append(Component.gray(" from "))
                .append(Component.yellow(entry.other || "Unknown"))
            } else if (entry.type === "shop_sell") {
              msg.append(Component.green("+" + formatBalance(entry.amount)))
                .append(Component.gray(" sold "))
                .append(Component.white(entry.desc || "items"))
                .append(Component.gray(" to "))
                .append(Component.yellow(entry.other || "Unknown"))
            } else if (entry.type === "admin_set") {
              msg.append(Component.aqua(formatBalance(entry.amount)))
                .append(Component.gray(" balance set by admin"))
            } else if (entry.type === "admin_add") {
              msg.append(Component.green("+" + formatBalance(entry.amount)))
                .append(Component.gray(" added by admin"))
            } else if (entry.type === "admin_subtract") {
              msg.append(Component.red("-" + formatBalance(entry.amount)))
                .append(Component.gray(" removed by admin"))
            } else if (entry.type === "withdraw") {
              msg.append(Component.red("-" + formatBalance(entry.amount)))
                .append(Component.gray(" withdrawn as coins"))
                .append(entry.desc ? Component.gray(" (" + entry.desc + ")") : Component.empty())
            } else if (entry.type === "deposit") {
              msg.append(Component.green("+" + formatBalance(entry.amount)))
                .append(Component.gray(" deposited from coins"))
            }

            ctx.getSource().sendSystemMessage(msg)
          }

          if (history.length > 10) {
            ctx.getSource().sendSystemMessage(Component.gray("... and " + (history.length - 10) + " more"))
          }

          return 1
        })
      )

      // /wallet withdraw <amount> [denomination] - Withdraw coins from balance
      .then(Commands.literal("withdraw")
        .then(
          Commands.argument("amount", Arguments.INTEGER.create(event))
            .executes(ctx => {
              // Withdraw with efficient coin split (no denomination specified)
              let player = ctx.getSource().getPlayer()
              if (player == null) {
                ctx.getSource().sendFailure(Component.red("This command can only be used by players"))
                return 0
              }

              let withdrawAmount = Arguments.INTEGER.getResult(ctx, "amount")
              if (withdrawAmount <= 0) {
                ctx.getSource().sendFailure(Component.red("Amount must be positive"))
                return 0
              }

              let srv = ctx.getSource().getServer()
              let pUuid = player.getStringUuid()
              let currentBalance = getBalance(srv, pUuid)

              if (currentBalance < withdrawAmount) {
                ctx.getSource().sendFailure(
                  Component.empty()
                    .append(Component.red("Insufficient balance. You have "))
                    .append(Component.yellow(formatBalance(currentBalance)))
                )
                return 0
              }

              // Remove balance and give coins
              removeBalance(srv, pUuid, withdrawAmount)
              giveCoinsEfficient(player, withdrawAmount)

              // Record history
              addHistoryEntry(srv, pUuid, "withdraw", withdrawAmount, null, "Coins withdrawn")

              // Build breakdown message
              let remaining = withdrawAmount
              let parts = []
              for (let i = 0; i < COIN_DENOMINATIONS.length; i++) {
                let denom = COIN_DENOMINATIONS[i]
                if (remaining >= denom.value) {
                  let count = Math.floor(remaining / denom.value)
                  remaining = remaining % denom.value
                  parts.push(count + "x $" + denom.value)
                }
              }

              player.sendSystemMessage(
                Component.empty()
                  .append(Component.gold("Withdrew "))
                  .append(Component.green(formatBalance(withdrawAmount)))
                  .append(Component.gold(" as coins: "))
                  .append(Component.yellow(parts.join(", ")))
              )

              return 1
            })
            .then(
              Commands.argument("denomination", Arguments.INTEGER.create(event))
                .executes(ctx => {
                  // Withdraw with specific denomination
                  let player = ctx.getSource().getPlayer()
                  if (player == null) {
                    ctx.getSource().sendFailure(Component.red("This command can only be used by players"))
                    return 0
                  }

                  let withdrawAmount = Arguments.INTEGER.getResult(ctx, "amount")
                  let denomination = Arguments.INTEGER.getResult(ctx, "denomination")

                  if (withdrawAmount <= 0) {
                    ctx.getSource().sendFailure(Component.red("Amount must be positive"))
                    return 0
                  }

                  // Validate denomination
                  let validDenom = false
                  for (let i = 0; i < COIN_DENOMINATIONS.length; i++) {
                    if (COIN_DENOMINATIONS[i].value === denomination) {
                      validDenom = true
                      break
                    }
                  }
                  if (!validDenom) {
                    ctx.getSource().sendFailure(Component.red("Invalid denomination. Use 1, 10, 100, 1000, or 10000"))
                    return 0
                  }

                  // Check if amount is divisible by denomination
                  if (withdrawAmount % denomination !== 0) {
                    ctx.getSource().sendFailure(
                      Component.empty()
                        .append(Component.red("Amount "))
                        .append(Component.yellow(formatBalance(withdrawAmount)))
                        .append(Component.red(" is not divisible by "))
                        .append(Component.yellow("$" + denomination))
                    )
                    return 0
                  }

                  let srv = ctx.getSource().getServer()
                  let pUuid = player.getStringUuid()
                  let currentBalance = getBalance(srv, pUuid)

                  if (currentBalance < withdrawAmount) {
                    ctx.getSource().sendFailure(
                      Component.empty()
                        .append(Component.red("Insufficient balance. You have "))
                        .append(Component.yellow(formatBalance(currentBalance)))
                    )
                    return 0
                  }

                  // Remove balance and give specific coins
                  removeBalance(srv, pUuid, withdrawAmount)
                  giveCoinsSpecific(player, withdrawAmount, denomination)

                  // Record history
                  let coinCount = withdrawAmount / denomination
                  addHistoryEntry(srv, pUuid, "withdraw", withdrawAmount, null, coinCount + "x $" + denomination + " coins")

                  player.sendSystemMessage(
                    Component.empty()
                      .append(Component.gold("Withdrew "))
                      .append(Component.green(formatBalance(withdrawAmount)))
                      .append(Component.gold(" as "))
                      .append(Component.yellow(coinCount + "x $" + denomination + " coins"))
                  )

                  return 1
                })
            )
        )
      )

      // /wallet deposit [amount] - Deposit coins to balance
      .then(Commands.literal("deposit")
        .executes(ctx => {
          // Deposit all coins (no amount specified)
          let player = ctx.getSource().getPlayer()
          if (player == null) {
            ctx.getSource().sendFailure(Component.red("This command can only be used by players"))
            return 0
          }

          let srv = ctx.getSource().getServer()
          let pUuid = player.getStringUuid()

          let coinInfo = countPlayerCoins(player)
          if (coinInfo.total <= 0) {
            ctx.getSource().sendFailure(Component.red("You don't have any coins to deposit"))
            return 0
          }

          // Remove all coins and add balance
          removeCoinsFromPlayer(player, coinInfo.total)
          addBalance(srv, pUuid, coinInfo.total)

          // Record history
          addHistoryEntry(srv, pUuid, "deposit", coinInfo.total, null, "All coins deposited")

          player.sendSystemMessage(
            Component.empty()
              .append(Component.gold("Deposited "))
              .append(Component.green(formatBalance(coinInfo.total)))
              .append(Component.gold(" from coins"))
          )

          return 1
        })
        .then(
          Commands.argument("amount", Arguments.INTEGER.create(event))
            .executes(ctx => {
              // Deposit specific amount
              let player = ctx.getSource().getPlayer()
              if (player == null) {
                ctx.getSource().sendFailure(Component.red("This command can only be used by players"))
                return 0
              }

              let depositAmount = Arguments.INTEGER.getResult(ctx, "amount")
              if (depositAmount <= 0) {
                ctx.getSource().sendFailure(Component.red("Amount must be positive"))
                return 0
              }

              let srv = ctx.getSource().getServer()
              let pUuid = player.getStringUuid()

              let coinInfo = countPlayerCoins(player)
              if (coinInfo.total < depositAmount) {
                ctx.getSource().sendFailure(
                  Component.empty()
                    .append(Component.red("You don't have enough coins. You have "))
                    .append(Component.yellow(formatBalance(coinInfo.total)))
                    .append(Component.red(" in coins"))
                )
                return 0
              }

              // Check if exact payment is possible
              if (!canPayExactWithCoins(player, depositAmount)) {
                ctx.getSource().sendFailure(
                  Component.empty()
                    .append(Component.red("Cannot deposit exact amount "))
                    .append(Component.yellow(formatBalance(depositAmount)))
                    .append(Component.red(". You need exact change."))
                )
                return 0
              }

              // Remove coins and add balance
              removeCoinsFromPlayer(player, depositAmount)
              addBalance(srv, pUuid, depositAmount)

              // Record history
              addHistoryEntry(srv, pUuid, "deposit", depositAmount, null, "Coins deposited")

              player.sendSystemMessage(
                Component.empty()
                  .append(Component.gold("Deposited "))
                  .append(Component.green(formatBalance(depositAmount)))
                  .append(Component.gold(" from coins"))
              )

              return 1
            })
        )
      )

      // /wallet admin - Admin subcommands
      .then(Commands.literal("admin")
        .requires(src => src.hasPermission(2))

        // /wallet admin (no args) - show admin help
        .executes(ctx => {
          let src = ctx.getSource()
          src.sendSystemMessage(Component.gold("=== Wallet Admin Commands ==="))
          src.sendSystemMessage(Component.yellow("/wallet admin getbalance <player>").append(Component.gray(" - Check player's balance")))
          src.sendSystemMessage(Component.yellow("/wallet admin setbalance <player> <amount>").append(Component.gray(" - Set balance")))
          src.sendSystemMessage(Component.yellow("/wallet admin addbalance <player> <amount>").append(Component.gray(" - Add to balance")))
          src.sendSystemMessage(Component.yellow("/wallet admin subtractbalance <player> <amount>").append(Component.gray(" - Subtract from balance")))
          src.sendSystemMessage(Component.yellow("/wallet admin history <player>").append(Component.gray(" - View player's history")))
          src.sendSystemMessage(Component.yellow("/wallet admin shop list [player]").append(Component.gray(" - List shops")))
          return 1
        })

        // /wallet admin getbalance <player>
        .then(Commands.literal("getbalance")
          .then(
            Commands.argument("player", Arguments.GAME_PROFILE.create(event))
              .executes(ctx => {
                let profiles = Arguments.GAME_PROFILE.getResult(ctx, "player")

                let profileArray = profiles.toArray()
                if (profileArray.length === 0) {
                  ctx.getSource().sendFailure(Component.red("No player found"))
                  return 0
                }

                let srv = ctx.getSource().getServer()
                let prof = profileArray[0]
                let pUuid = prof.getId().toString()
                let pName = prof.getName()

                let bal = getBalance(srv, pUuid)

                let msg = Component.empty()
                  .append(Component.yellow(pName))
                  .append(Component.gold("'s balance: "))
                  .append(Component.green(formatBalance(bal)))

                ctx.getSource().sendSystemMessage(msg)
                return 1
              })
          )
        )

        // /wallet admin setbalance <player> <amount>
        .then(Commands.literal("setbalance")
          .then(
            Commands.argument("player", Arguments.GAME_PROFILE.create(event))
              .then(
                Commands.argument("amount", Arguments.INTEGER.create(event))
                  .executes(ctx => {
                    let profiles = Arguments.GAME_PROFILE.getResult(ctx, "player")
                    let amt = Arguments.INTEGER.getResult(ctx, "amount")

                    if (amt < 0) {
                      ctx.getSource().sendFailure(Component.red("Amount cannot be negative"))
                      return 0
                    }

                    let profileArray = profiles.toArray()
                    if (profileArray.length === 0) {
                      ctx.getSource().sendFailure(Component.red("No player found"))
                      return 0
                    }

                    let srv = ctx.getSource().getServer()
                    let prof = profileArray[0]
                    let pUuid = prof.getId().toString()
                    let pName = prof.getName()

                    let oldBal = getBalance(srv, pUuid)
                    setBalance(srv, pUuid, amt)

                    // Record in history
                    addHistoryEntry(srv, pUuid, "admin_set", amt, "Admin", "Balance set from " + formatBalance(oldBal))

                    let msg = Component.empty()
                      .append(Component.gold("Set "))
                      .append(Component.yellow(pName))
                      .append(Component.gold("'s balance to "))
                      .append(Component.green(formatBalance(amt)))

                    ctx.getSource().sendSystemMessage(msg)
                    return 1
                  })
              )
          )
        )

        // /wallet admin addbalance <player> <amount>
        .then(Commands.literal("addbalance")
          .then(
            Commands.argument("player", Arguments.GAME_PROFILE.create(event))
              .then(
                Commands.argument("amount", Arguments.INTEGER.create(event))
                  .executes(ctx => {
                    let profiles = Arguments.GAME_PROFILE.getResult(ctx, "player")
                    let amt = Arguments.INTEGER.getResult(ctx, "amount")

                    if (amt <= 0) {
                      ctx.getSource().sendFailure(Component.red("Amount must be positive"))
                      return 0
                    }

                    let profileArray = profiles.toArray()
                    if (profileArray.length === 0) {
                      ctx.getSource().sendFailure(Component.red("No player found"))
                      return 0
                    }

                    let srv = ctx.getSource().getServer()
                    let prof = profileArray[0]
                    let pUuid = prof.getId().toString()
                    let pName = prof.getName()

                    let oldBal = getBalance(srv, pUuid)
                    addBalance(srv, pUuid, amt)
                    let newBal = getBalance(srv, pUuid)

                    // Record in history
                    addHistoryEntry(srv, pUuid, "admin_add", amt, "Admin", null)

                    let msg = Component.empty()
                      .append(Component.gold("Added "))
                      .append(Component.green(formatBalance(amt)))
                      .append(Component.gold(" to "))
                      .append(Component.yellow(pName))
                      .append(Component.gold("'s balance ("))
                      .append(Component.gray(formatBalance(oldBal)))
                      .append(Component.gold(" -> "))
                      .append(Component.green(formatBalance(newBal)))
                      .append(Component.gold(")"))

                    ctx.getSource().sendSystemMessage(msg)
                    return 1
                  })
              )
          )
        )

        // /wallet admin subtractbalance <player> <amount>
        .then(Commands.literal("subtractbalance")
          .then(
            Commands.argument("player", Arguments.GAME_PROFILE.create(event))
              .then(
                Commands.argument("amount", Arguments.INTEGER.create(event))
                  .executes(ctx => {
                    let profiles = Arguments.GAME_PROFILE.getResult(ctx, "player")
                    let amt = Arguments.INTEGER.getResult(ctx, "amount")

                    if (amt <= 0) {
                      ctx.getSource().sendFailure(Component.red("Amount must be positive"))
                      return 0
                    }

                    let profileArray = profiles.toArray()
                    if (profileArray.length === 0) {
                      ctx.getSource().sendFailure(Component.red("No player found"))
                      return 0
                    }

                    let srv = ctx.getSource().getServer()
                    let prof = profileArray[0]
                    let pUuid = prof.getId().toString()
                    let pName = prof.getName()

                    let oldBal = getBalance(srv, pUuid)
                    if (oldBal < amt) {
                      ctx.getSource().sendFailure(
                        Component.empty()
                          .append(Component.red("Cannot subtract "))
                          .append(Component.yellow(formatBalance(amt)))
                          .append(Component.red(" from "))
                          .append(Component.yellow(pName))
                          .append(Component.red(" (has "))
                          .append(Component.yellow(formatBalance(oldBal)))
                          .append(Component.red(")"))
                      )
                      return 0
                    }

                    removeBalance(srv, pUuid, amt)
                    let newBal = getBalance(srv, pUuid)

                    // Record in history
                    addHistoryEntry(srv, pUuid, "admin_subtract", amt, "Admin", null)

                    let msg = Component.empty()
                      .append(Component.gold("Subtracted "))
                      .append(Component.red(formatBalance(amt)))
                      .append(Component.gold(" from "))
                      .append(Component.yellow(pName))
                      .append(Component.gold("'s balance ("))
                      .append(Component.gray(formatBalance(oldBal)))
                      .append(Component.gold(" -> "))
                      .append(Component.green(formatBalance(newBal)))
                      .append(Component.gold(")"))

                    ctx.getSource().sendSystemMessage(msg)
                    return 1
                  })
              )
          )
        )

        // /wallet admin history <player> - View player's transaction history
        .then(Commands.literal("history")
          .then(
            Commands.argument("player", Arguments.GAME_PROFILE.create(event))
              .executes(ctx => {
                let profiles = Arguments.GAME_PROFILE.getResult(ctx, "player")

                let profileArray = profiles.toArray()
                if (profileArray.length === 0) {
                  ctx.getSource().sendFailure(Component.red("No player found"))
                  return 0
                }

                let srv = ctx.getSource().getServer()
                let prof = profileArray[0]
                let pUuid = prof.getId().toString()
                let pName = prof.getName()
                let history = getHistory(srv, pUuid)

                ctx.getSource().sendSystemMessage(
                  Component.gold("=== Transaction History for ")
                    .append(Component.yellow(pName))
                    .append(Component.gold(" ==="))
                )

                if (history.length === 0) {
                  ctx.getSource().sendSystemMessage(Component.gray("No transactions yet"))
                  return 1
                }

                // Show last 15 transactions for admin
                let toShow = Math.min(history.length, 15)
                for (let i = 0; i < toShow; i++) {
                  let entry = history[i]
                  let timeStr = formatTimestamp(entry.time)
                  let msg = Component.empty().append(Component.gray("[" + timeStr + "] "))

                  if (entry.type === "pay_sent") {
                    msg.append(Component.red("-" + formatBalance(entry.amount)))
                      .append(Component.gray(" sent to "))
                      .append(Component.yellow(entry.other))
                  } else if (entry.type === "pay_received") {
                    msg.append(Component.green("+" + formatBalance(entry.amount)))
                      .append(Component.gray(" from "))
                      .append(Component.yellow(entry.other))
                  } else if (entry.type === "shop_buy") {
                    msg.append(Component.red("-" + formatBalance(entry.amount)))
                      .append(Component.gray(" bought "))
                      .append(Component.white(entry.desc || "items"))
                      .append(Component.gray(" from "))
                      .append(Component.yellow(entry.other || "Unknown"))
                  } else if (entry.type === "shop_sell") {
                    msg.append(Component.green("+" + formatBalance(entry.amount)))
                      .append(Component.gray(" sold "))
                      .append(Component.white(entry.desc || "items"))
                      .append(Component.gray(" to "))
                      .append(Component.yellow(entry.other || "Unknown"))
                  } else if (entry.type === "admin_set") {
                    msg.append(Component.aqua(formatBalance(entry.amount)))
                      .append(Component.gray(" balance set by admin"))
                  } else if (entry.type === "admin_add") {
                    msg.append(Component.green("+" + formatBalance(entry.amount)))
                      .append(Component.gray(" added by admin"))
                  } else if (entry.type === "admin_subtract") {
                    msg.append(Component.red("-" + formatBalance(entry.amount)))
                      .append(Component.gray(" removed by admin"))
                  }

                  ctx.getSource().sendSystemMessage(msg)
                }

                if (history.length > 15) {
                  ctx.getSource().sendSystemMessage(Component.gray("... and " + (history.length - 15) + " more"))
                }

                return 1
              })
          )
        )

        // /wallet admin shop - Shop admin subcommands
        .then(Commands.literal("shop")
          // /wallet admin shop list [player] - List all shops or shops by player
          .then(Commands.literal("list")
            .executes(ctx => {
              // List all shops
              let srv = ctx.getSource().getServer()
              ensureDataLoaded(srv)

              ctx.getSource().sendSystemMessage(Component.gold("=== All Shops ==="))

              let shopKeys = Object.keys(shopsCache)
              if (shopKeys.length === 0) {
                ctx.getSource().sendSystemMessage(Component.gray("No shops registered"))
                return 1
              }

              for (let i = 0; i < shopKeys.length; i++) {
                let signKey = shopKeys[i]
                let shop = shopsCache[signKey]

                // Parse position from key: x_y_z_dimension
                let posParts = signKey.split("_")
                let x = posParts[0]
                let y = posParts[1]
                let z = posParts[2]
                let dim = posParts.slice(3).join("_")

                // Get owner name
                let ownerName = "Unknown"
                let ownerPlayer = srv.getPlayer(shop.owner)
                if (ownerPlayer) {
                  ownerName = ownerPlayer.getName().getString()
                } else {
                  try {
                    let profileCache = srv.getProfileCache()
                    if (profileCache) {
                      let optProfile = profileCache.get(Java.loadClass('java.util.UUID').fromString(shop.owner))
                      if (optProfile && optProfile.isPresent()) {
                        ownerName = optProfile.get().getName()
                      }
                    }
                  } catch(e) {
                    ownerName = shop.owner.substring(0, 8) + "..."
                  }
                }

                // Get item names
                let template = JSON.parse(shop.itemTemplate)
                let itemNames = []
                for (let j = 0; j < template.length; j++) {
                  let itemId = template[j].id
                  let simpleName = itemId.replace("minecraft:", "").replace(/_/g, " ")
                  simpleName = simpleName.split(" ").map(function(word) {
                    return word.charAt(0).toUpperCase() + word.slice(1)
                  }).join(" ")
                  itemNames.push(simpleName)
                }
                let itemsStr = itemNames.join(", ")
                if (itemsStr.length > 30) {
                  itemsStr = itemsStr.substring(0, 27) + "..."
                }

                // Build clickable teleport command
                let tpCmd = "/tp @s " + x + " " + y + " " + z

                // Create clickable teleport link
                let tpLink = Component.lightPurple("[TP]")
                  .clickRunCommand(tpCmd)
                  .hover(Component.gray("Click to teleport to " + x + ", " + y + ", " + z))

                // Create message with coordinates
                let shopMsg = Component.empty()
                  .append(Component.yellow("[" + shop.type + "] "))
                  .append(Component.white(itemsStr))
                  .append(Component.gray(" - "))
                  .append(Component.green(shop.price + "$"))
                  .append(Component.gray(" by "))
                  .append(Component.aqua(ownerName))
                  .append(Component.gray(" "))
                  .append(tpLink)

                ctx.getSource().sendSystemMessage(shopMsg)
              }

              ctx.getSource().sendSystemMessage(Component.gray("Total: " + shopKeys.length + " shops"))
              return 1
            })
            .then(
              Commands.argument("player", Arguments.GAME_PROFILE.create(event))
                .executes(ctx => {
                  let profiles = Arguments.GAME_PROFILE.getResult(ctx, "player")

                  let profileArray = profiles.toArray()
                  if (profileArray.length === 0) {
                    ctx.getSource().sendFailure(Component.red("No player found"))
                    return 0
                  }

                  let srv = ctx.getSource().getServer()
                  ensureDataLoaded(srv)

                  let prof = profileArray[0]
                  let pUuid = prof.getId().toString()
                  let pName = prof.getName()

                  ctx.getSource().sendSystemMessage(
                    Component.gold("=== Shops owned by ")
                      .append(Component.yellow(pName))
                      .append(Component.gold(" ==="))
                  )

                  let count = 0
                  for (let signKey in shopsCache) {
                    let shop = shopsCache[signKey]
                    if (shop.owner !== pUuid) continue
                    count++

                    // Parse position from key
                    let posParts = signKey.split("_")
                    let x = posParts[0]
                    let y = posParts[1]
                    let z = posParts[2]

                    // Get item names
                    let template = JSON.parse(shop.itemTemplate)
                    let itemNames = []
                    for (let j = 0; j < template.length; j++) {
                      let itemId = template[j].id
                      let simpleName = itemId.replace("minecraft:", "").replace(/_/g, " ")
                      simpleName = simpleName.split(" ").map(function(word) {
                        return word.charAt(0).toUpperCase() + word.slice(1)
                      }).join(" ")
                      itemNames.push(simpleName)
                    }
                    let itemsStr = itemNames.join(", ")
                    if (itemsStr.length > 30) {
                      itemsStr = itemsStr.substring(0, 27) + "..."
                    }

                    // Build clickable teleport command
                    let tpCmd = "/tp @s " + x + " " + y + " " + z

                    // Create clickable teleport link
                    let tpLink = Component.lightPurple("[TP]")
                      .clickRunCommand(tpCmd)
                      .hover(Component.gray("Click to teleport to " + x + ", " + y + ", " + z))

                    let shopMsg = Component.empty()
                      .append(Component.yellow("[" + shop.type + "] "))
                      .append(Component.white(itemsStr))
                      .append(Component.gray(" - "))
                      .append(Component.green(shop.price + "$"))
                      .append(Component.gray(" "))
                      .append(tpLink)

                    ctx.getSource().sendSystemMessage(shopMsg)
                  }

                  if (count === 0) {
                    ctx.getSource().sendSystemMessage(Component.gray("No shops found for this player"))
                  } else {
                    ctx.getSource().sendSystemMessage(Component.gray("Total: " + count + " shops"))
                  }

                  return 1
                })
            )
          )
        )
      )
  )

})

console.info("[KubeShop] Economy & Shop system loaded")
