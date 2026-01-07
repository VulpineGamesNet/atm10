// Discord Chat Sync - Minecraft <-> Discord Integration
// Minecraft -> Discord: via webhooks
// Discord -> Minecraft: via RCON command /discordmsg (called by external Python bot)

// ============================================================================
// CONFIGURATION
// ============================================================================

const DISCORD_CONFIG = {
  // Discord webhook URL for sending MC messages to Discord
  // Create a webhook in Discord: Channel Settings -> Integrations -> Webhooks
  webhookUrl: "YOUR_WEBHOOK_URL_HERE",

  // Enable/disable features
  enableChatSync: true,
  enableJoinLeave: true,

  // Server info
  serverName: "ATM10 Server",

  // Stats file path (read by Python bot for channel topic updates)
  statsFilePath: "kubejs/server_data/server_stats.json",

  // Rate limiting: minimum milliseconds between webhook sends
  webhookCooldownMs: 1000,

  // Maximum message length to send to Discord
  maxMessageLength: 1900
}

// ============================================================================
// JAVA CLASS LOADING
// ============================================================================

let URL = null
let OutputStreamWriter = null
let BufferedReader = null
let InputStreamReader = null
let FileWriter = null
let File = null

try {
  URL = Java.loadClass('java.net.URL')
  OutputStreamWriter = Java.loadClass('java.io.OutputStreamWriter')
  BufferedReader = Java.loadClass('java.io.BufferedReader')
  InputStreamReader = Java.loadClass('java.io.InputStreamReader')
  FileWriter = Java.loadClass('java.io.FileWriter')
  File = Java.loadClass('java.io.File')
  console.info("[DiscordChat] Java classes loaded successfully")
} catch (e) {
  console.error("[DiscordChat] Failed to load Java classes: " + e)
}

// ============================================================================
// STATE VARIABLES
// ============================================================================

let serverStartTime = Date.now()
let lastWebhookTime = 0
let messageQueue = []

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

// Escape special characters for JSON strings (Rhino-compatible, no regex)
function escapeJson(str) {
  if (!str) return ""
  let result = ""
  for (let i = 0; i < str.length; i++) {
    let c = str.charAt(i)
    if (c === '"') result += '\\"'
    else if (c === '\\') result += '\\\\'
    else if (c === '\n') result += '\\n'
    else if (c === '\r') result += '\\r'
    else if (c === '\t') result += '\\t'
    else result += c
  }
  return result
}

// Strip Minecraft color codes (section symbol followed by character)
function stripColorCodes(str) {
  if (!str) return ""
  let result = ""
  let i = 0
  while (i < str.length) {
    let c = str.charAt(i)
    // Section symbol is \u00A7
    if (c === '\u00A7' && i + 1 < str.length) {
      // Skip the color code character
      i += 2
    } else {
      result += c
      i++
    }
  }
  return result
}

// Truncate message to max length
function truncateMessage(str, maxLen) {
  if (!str) return ""
  if (str.length <= maxLen) return str
  return str.substring(0, maxLen - 3) + "..."
}

// ============================================================================
// WEBHOOK FUNCTIONS
// ============================================================================

// Send HTTP POST request to Discord webhook
function sendWebhookDirect(content, username, avatarUrl) {
  if (!URL) {
    console.error("[DiscordChat] URL class not available")
    return false
  }

  if (!DISCORD_CONFIG.webhookUrl || DISCORD_CONFIG.webhookUrl === "YOUR_WEBHOOK_URL_HERE") {
    console.warn("[DiscordChat] Webhook URL not configured")
    return false
  }

  try {
    let url = new URL(DISCORD_CONFIG.webhookUrl)
    let conn = url.openConnection()
    conn.setRequestMethod("POST")
    conn.setRequestProperty("Content-Type", "application/json; charset=UTF-8")
    conn.setRequestProperty("User-Agent", "KubeJS-DiscordChat/1.0")
    conn.setDoOutput(true)
    conn.setConnectTimeout(5000)
    conn.setReadTimeout(5000)

    // Build JSON payload manually (Rhino-safe)
    let jsonStr = '{"content":"' + escapeJson(content) + '"'
    if (username) {
      jsonStr += ',"username":"' + escapeJson(username) + '"'
    }
    if (avatarUrl) {
      jsonStr += ',"avatar_url":"' + escapeJson(avatarUrl) + '"'
    }
    jsonStr += '}'

    // Write request body
    let outputStream = conn.getOutputStream()
    let writer = new OutputStreamWriter(outputStream, "UTF-8")
    writer.write(jsonStr)
    writer.flush()
    writer.close()

    // Read response
    let responseCode = conn.getResponseCode()
    conn.disconnect()

    if (responseCode >= 200 && responseCode < 300) {
      return true
    } else if (responseCode === 429) {
      console.warn("[DiscordChat] Rate limited by Discord")
      return false
    } else {
      console.warn("[DiscordChat] Webhook returned status: " + responseCode)
      return false
    }
  } catch (e) {
    console.error("[DiscordChat] Webhook error: " + e)
    return false
  }
}

// Queue a message for sending (with rate limiting)
function queueWebhookMessage(content, username, avatarUrl) {
  messageQueue.push({
    type: "message",
    content: content,
    username: username,
    avatarUrl: avatarUrl,
    timestamp: Date.now()
  })
}

// Queue an embed for sending (used for join/leave notifications)
function queueWebhookEmbed(description, color, iconUrl) {
  messageQueue.push({
    type: "embed",
    description: description,
    color: color,
    iconUrl: iconUrl,
    timestamp: Date.now()
  })
}

// Send embed to Discord webhook
function sendWebhookEmbed(description, color, iconUrl) {
  if (!URL) {
    console.error("[DiscordChat] URL class not available")
    return false
  }

  if (!DISCORD_CONFIG.webhookUrl || DISCORD_CONFIG.webhookUrl === "YOUR_WEBHOOK_URL_HERE") {
    console.warn("[DiscordChat] Webhook URL not configured")
    return false
  }

  try {
    let url = new URL(DISCORD_CONFIG.webhookUrl)
    let conn = url.openConnection()
    conn.setRequestMethod("POST")
    conn.setRequestProperty("Content-Type", "application/json; charset=UTF-8")
    conn.setRequestProperty("User-Agent", "KubeJS-DiscordChat/1.0")
    conn.setDoOutput(true)
    conn.setConnectTimeout(5000)
    conn.setReadTimeout(5000)

    // Build embed JSON payload
    // Format: {"embeds":[{"description":"text","color":65280,"thumbnail":{"url":"..."}}]}
    let jsonStr = '{"embeds":[{'
    jsonStr += '"description":"' + escapeJson(description) + '"'
    jsonStr += ',"color":' + color
    if (iconUrl) {
      jsonStr += ',"thumbnail":{"url":"' + escapeJson(iconUrl) + '"}'
    }
    jsonStr += '}]}'

    // Write request body
    let outputStream = conn.getOutputStream()
    let writer = new OutputStreamWriter(outputStream, "UTF-8")
    writer.write(jsonStr)
    writer.flush()
    writer.close()

    // Read response
    let responseCode = conn.getResponseCode()
    conn.disconnect()

    if (responseCode >= 200 && responseCode < 300) {
      return true
    } else if (responseCode === 429) {
      console.warn("[DiscordChat] Rate limited by Discord")
      return false
    } else {
      console.warn("[DiscordChat] Webhook returned status: " + responseCode)
      return false
    }
  } catch (e) {
    console.error("[DiscordChat] Webhook embed error: " + e)
    return false
  }
}

// Process the message queue (called from tick handler)
function processMessageQueue() {
  if (messageQueue.length === 0) return

  let now = Date.now()
  if (now - lastWebhookTime < DISCORD_CONFIG.webhookCooldownMs) return

  let msg = messageQueue.shift()
  let success = false

  if (msg.type === "embed") {
    success = sendWebhookEmbed(msg.description, msg.color, msg.iconUrl)
  } else {
    success = sendWebhookDirect(msg.content, msg.username, msg.avatarUrl)
  }

  if (success) {
    lastWebhookTime = now
  } else {
    // Re-queue on failure (but only if message is less than 30 seconds old)
    if (now - msg.timestamp < 30000) {
      messageQueue.unshift(msg)
    }
  }
}

// ============================================================================
// SERVER STATS FUNCTIONS
// ============================================================================

// Calculate server uptime
function getUptime() {
  let uptimeMs = Date.now() - serverStartTime
  let seconds = Math.floor(uptimeMs / 1000)
  let minutes = Math.floor(seconds / 60)
  let hours = Math.floor(minutes / 60)
  let days = Math.floor(hours / 24)

  hours = hours % 24
  minutes = minutes % 60

  if (days > 0) {
    return days + "d " + hours + "h " + minutes + "m"
  } else {
    return hours + "h " + minutes + "m"
  }
}

// Get TPS from server
function getTPS(server) {
  try {
    // server.getAverageTickTime() returns milliseconds per tick
    let avgTickMs = server.getAverageTickTime()

    // TPS = 1000ms / avgTickMs, capped at 20
    let tps = Math.min(20.0, 1000.0 / avgTickMs)

    // Round to 2 decimal places
    return Math.round(tps * 100) / 100
  } catch (e) {
    console.warn("[DiscordChat] Could not get TPS: " + e)
    return 20.00
  }
}

// Get online player count
function getPlayerCount(server) {
  try {
    let count = 0
    server.getPlayers().forEach(function (p) {
      count++
    })
    return count
  } catch (e) {
    return 0
  }
}

// Get list of online player names
function getPlayerList(server) {
  let names = []
  try {
    server.getPlayers().forEach(function (p) {
      names.push(p.getName().getString())
    })
  } catch (e) {
    // Return empty array on error
  }
  return names
}

// Write stats to JSON file
function writeStatsFile(server) {
  if (!FileWriter || !File) return

  try {
    let tps = getTPS(server)
    let playerCount = getPlayerCount(server)
    let players = getPlayerList(server)
    let uptime = getUptime()
    let timestamp = Date.now()

    // Build JSON manually (Rhino-safe)
    let playersJson = '['
    for (let i = 0; i < players.length; i++) {
      if (i > 0) playersJson += ','
      playersJson += '"' + escapeJson(players[i]) + '"'
    }
    playersJson += ']'

    let jsonStr = '{'
    jsonStr += '"tps":' + tps + ','
    jsonStr += '"playerCount":' + playerCount + ','
    jsonStr += '"players":' + playersJson + ','
    jsonStr += '"uptime":"' + escapeJson(uptime) + '",'
    jsonStr += '"timestamp":' + timestamp + ','
    jsonStr += '"serverName":"' + escapeJson(DISCORD_CONFIG.serverName) + '"'
    jsonStr += '}'

    // Ensure directory exists
    let file = new File(DISCORD_CONFIG.statsFilePath)
    let parentDir = file.getParentFile()
    if (parentDir && !parentDir.exists()) {
      parentDir.mkdirs()
    }

    // Write to file
    let writer = new FileWriter(file)
    writer.write(jsonStr)
    writer.close()

  } catch (e) {
    console.error("[DiscordChat] Failed to write stats file: " + e)
  }
}

// ============================================================================
// EVENT HANDLERS
// ============================================================================

// Server loaded - initialize
ServerEvents.loaded(event => {
  serverStartTime = Date.now()
  console.info("[DiscordChat] Discord chat sync initialized")

  // Write initial stats
  writeStatsFile(event.server)
})

// Server tick - process message queue and update stats
ServerEvents.tick(event => {
  let tickCount = event.server.getTickCount()

  // Process webhook queue every tick
  processMessageQueue()

  // Update stats every 5 seconds (100 ticks)
  if (tickCount % 100 === 0) {
    writeStatsFile(event.server)
  }
})

// Player chat messages
ServerEvents.chat(event => {
  if (!DISCORD_CONFIG.enableChatSync) return

  let player = event.player
  let message = event.message

  // Get the raw message string
  let messageStr = ""
  try {
    // Try to get string representation
    if (typeof message === 'string') {
      messageStr = message
    } else if (message.getString) {
      messageStr = message.getString()
    } else if (message.getContents) {
      messageStr = message.getContents().toString()
    } else {
      messageStr = message.toString()
    }
  } catch (e) {
    messageStr = message.toString()
  }

  // Clean up the message
  messageStr = stripColorCodes(messageStr)
  messageStr = truncateMessage(messageStr, DISCORD_CONFIG.maxMessageLength)

  if (!messageStr || messageStr.length === 0) return

  let playerName = player.getName().getString()
  let playerUuid = player.getStringUuid()

  // Get player's Minecraft head as avatar URL
  let avatarUrl = "https://crafatar.com/avatars/" + playerUuid + "?size=128&overlay"

  // Queue message for Discord
  queueWebhookMessage(messageStr, playerName, avatarUrl)
})

// Discord embed colors (decimal values)
const EMBED_COLOR_GREEN = 5763719   // #57F287 - Discord green
const EMBED_COLOR_RED = 15548997    // #ED4245 - Discord red

// Player join
PlayerEvents.loggedIn(event => {
  if (!DISCORD_CONFIG.enableJoinLeave) return

  let player = event.player
  let playerName = player.getName().getString()
  let playerUuid = player.getStringUuid()

  // Player head icon URL
  let iconUrl = "https://crafatar.com/avatars/" + playerUuid + "?size=64&overlay"

  // Send join notification as embed with green bar
  queueWebhookEmbed(
    ":green_circle: **" + playerName + "** logged in",
    EMBED_COLOR_GREEN,
    iconUrl
  )
})

// Player leave
PlayerEvents.loggedOut(event => {
  if (!DISCORD_CONFIG.enableJoinLeave) return

  let player = event.player
  let playerName = player.getName().getString()
  let playerUuid = player.getStringUuid()

  // Player head icon URL
  let iconUrl = "https://crafatar.com/avatars/" + playerUuid + "?size=64&overlay"

  // Send leave notification as embed with red bar
  queueWebhookEmbed(
    ":red_circle: **" + playerName + "** logged out",
    EMBED_COLOR_RED,
    iconUrl
  )
})

// ============================================================================
// COMMANDS - For receiving messages from Discord bot via RCON
// ============================================================================

ServerEvents.commandRegistry(event => {
  let Commands = event.getCommands()
  let Arguments = event.getArguments()

  // /discordmsg <username> <message>
  // Internal command called by Discord bot via RCON
  event.register(
    Commands.literal("discordmsg")
      .requires(function (src) {
        // Only allow from console/RCON (permission level 4)
        return src.hasPermission(4)
      })
      .then(
        Commands.argument("username", Arguments.STRING.create(event))
          .then(
            Commands.argument("message", Arguments.GREEDY_STRING.create(event))
              .executes(function (ctx) {
                let username = Arguments.STRING.getResult(ctx, "username")
                let message = Arguments.GREEDY_STRING.getResult(ctx, "message")
                let server = ctx.getSource().getServer()

                // Build Discord-style message for MC chat
                let chatMsg = Component.empty()
                  .append(Component.gray("["))
                  .append(Component.blue("Discord"))
                  .append(Component.gray("] "))
                  .append(Component.aqua(username))
                  .append(Component.white(": "))
                  .append(Component.white(message))

                // Broadcast to all players
                server.getPlayers().forEach(function (player) {
                  player.sendSystemMessage(chatMsg)
                })

                // Log to console
                console.info("[Discord] " + username + ": " + message)

                return 1
              })
          )
      )
  )

  // /discordstatus - Check Discord integration status (admin only)
  event.register(
    Commands.literal("discordstatus")
      .requires(function (src) {
        return src.hasPermission(2)
      })
      .executes(function (ctx) {
        let src = ctx.getSource()

        src.sendSystemMessage(Component.gold("=== Discord Chat Status ==="))
        src.sendSystemMessage(
          Component.yellow("Chat Sync: ").append(
            DISCORD_CONFIG.enableChatSync ? Component.green("Enabled") : Component.red("Disabled")
          )
        )
        src.sendSystemMessage(
          Component.yellow("Join/Leave: ").append(
            DISCORD_CONFIG.enableJoinLeave ? Component.green("Enabled") : Component.red("Disabled")
          )
        )
        src.sendSystemMessage(
          Component.yellow("Webhook Configured: ").append(
            (DISCORD_CONFIG.webhookUrl && DISCORD_CONFIG.webhookUrl !== "YOUR_WEBHOOK_URL_HERE")
              ? Component.green("Yes")
              : Component.red("No")
          )
        )
        src.sendSystemMessage(
          Component.yellow("Message Queue: ").append(
            Component.white(messageQueue.length + " pending")
          )
        )
        src.sendSystemMessage(
          Component.yellow("Uptime: ").append(
            Component.white(getUptime())
          )
        )

        return 1
      })
  )
})

console.info("[DiscordChat] Discord chat sync script loaded")
