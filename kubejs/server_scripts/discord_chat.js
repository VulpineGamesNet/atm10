// Discord Chat Sync - Minecraft <-> Discord Integration
// Minecraft -> Discord: via RCON /getstats command (polled by Python bot)
// Discord -> Minecraft: via RCON /discordmsg command (called by Python bot)

// ============================================================================
// CONFIGURATION
// ============================================================================

const DISCORD_CONFIG = {
  // Enable/disable features
  enableChatSync: true,
  enableJoinLeave: true,

  // Server info
  serverName: "ATM10 Server",

  // Maximum message length
  maxMessageLength: 1900
}

// ============================================================================
// STATE VARIABLES
// ============================================================================

let serverStartTime = Date.now()
let pendingMessages = []

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

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

function stripColorCodes(str) {
  if (!str) return ""
  let result = ""
  let i = 0
  while (i < str.length) {
    let c = str.charAt(i)
    if (c === '\u00A7' && i + 1 < str.length) {
      i += 2
    } else {
      result += c
      i++
    }
  }
  return result
}

function truncateMessage(str, maxLen) {
  if (!str) return ""
  if (str.length <= maxLen) return str
  return str.substring(0, maxLen - 3) + "..."
}

// ============================================================================
// SERVER STATS FUNCTIONS
// ============================================================================

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

function getTPS(server) {
  try {
    let avgTickMs = server.getAverageTickTime()
    let tps = Math.min(20.0, 1000.0 / avgTickMs)
    return Math.round(tps * 100) / 100
  } catch (e) {
    return 20.00
  }
}

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

function getPlayerList(server) {
  let names = []
  try {
    server.getPlayers().forEach(function (p) {
      names.push(p.getName().getString())
    })
  } catch (e) {}
  return names
}

// Build JSON response for /getstats command
function buildStatsJson(server) {
  let tps = getTPS(server)
  let playerCount = getPlayerCount(server)
  let players = getPlayerList(server)
  let uptime = getUptime()

  // Build players array JSON
  let playersJson = '['
  for (let i = 0; i < players.length; i++) {
    if (i > 0) playersJson += ','
    playersJson += '"' + escapeJson(players[i]) + '"'
  }
  playersJson += ']'

  // Build messages array JSON
  let messagesJson = '['
  for (let i = 0; i < pendingMessages.length; i++) {
    if (i > 0) messagesJson += ','
    let msg = pendingMessages[i]
    messagesJson += '{"type":"' + escapeJson(msg.type) + '"'
    messagesJson += ',"player":"' + escapeJson(msg.player) + '"'
    messagesJson += ',"uuid":"' + escapeJson(msg.uuid) + '"'
    if (msg.message) {
      messagesJson += ',"message":"' + escapeJson(msg.message) + '"'
    }
    messagesJson += '}'
  }
  messagesJson += ']'

  // Build main JSON
  let jsonStr = '{'
  jsonStr += '"tps":' + tps + ','
  jsonStr += '"playerCount":' + playerCount + ','
  jsonStr += '"players":' + playersJson + ','
  jsonStr += '"uptime":"' + escapeJson(uptime) + '",'
  jsonStr += '"serverName":"' + escapeJson(DISCORD_CONFIG.serverName) + '",'
  jsonStr += '"messages":' + messagesJson
  jsonStr += '}'

  // Clear messages after building response (atomic read & clear)
  pendingMessages = []

  return jsonStr
}

// Queue a message for Python bot to send to Discord
function queueMessage(type, playerName, playerUuid, message) {
  pendingMessages.push({
    type: type,
    player: playerName,
    uuid: playerUuid,
    message: message || null
  })
}

// ============================================================================
// EVENT HANDLERS
// ============================================================================

// Server loaded - initialize
ServerEvents.loaded(event => {
  serverStartTime = Date.now()
  console.info("[DiscordChat] Discord chat sync initialized")
})

// Player chat messages
PlayerEvents.chat(event => {
  if (!DISCORD_CONFIG.enableChatSync) return

  let player = event.player
  let message = event.message

  // Get the raw message string
  let messageStr = ""
  try {
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

  messageStr = stripColorCodes(messageStr)
  messageStr = truncateMessage(messageStr, DISCORD_CONFIG.maxMessageLength)

  if (!messageStr || messageStr.length === 0) return

  let playerName = player.getName().getString()
  let playerUuid = player.getStringUuid()

  queueMessage("chat", playerName, playerUuid, messageStr)
})

// Player join
PlayerEvents.loggedIn(event => {
  if (!DISCORD_CONFIG.enableJoinLeave) return

  let player = event.player
  let playerName = player.getName().getString()
  let playerUuid = player.getStringUuid()

  queueMessage("join", playerName, playerUuid)
})

// Player leave
PlayerEvents.loggedOut(event => {
  if (!DISCORD_CONFIG.enableJoinLeave) return

  let player = event.player
  let playerName = player.getName().getString()
  let playerUuid = player.getStringUuid()

  queueMessage("leave", playerName, playerUuid)
})

// ============================================================================
// COMMANDS
// ============================================================================

ServerEvents.commandRegistry(event => {
  let Commands = event.getCommands()
  let Arguments = event.getArguments()

  // /getstats - Returns server stats and pending messages as JSON (for Python bot)
  // Clears the message queue after returning
  event.register(
    Commands.literal("getstats")
      .requires(function (src) {
        // Only allow from console/RCON (permission level 4)
        return src.hasPermission(4)
      })
      .executes(function (ctx) {
        let server = ctx.getSource().getServer()
        let jsonResponse = buildStatsJson(server)

        // Return JSON as command feedback
        ctx.getSource().sendSystemMessage(Component.literal(jsonResponse))

        return 1
      })
  )

  // /discordmsg <username> <message> - Relay message from Discord to Minecraft
  event.register(
    Commands.literal("discordmsg")
      .requires(function (src) {
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

                let chatMsg = Component.empty()
                  .append(Component.gray("["))
                  .append(Component.blue("Discord"))
                  .append(Component.gray("] "))
                  .append(Component.aqua(username))
                  .append(Component.white(": "))
                  .append(Component.white(message))

                server.getPlayers().forEach(function (player) {
                  player.sendSystemMessage(chatMsg)
                })

                console.info("[Discord] " + username + ": " + message)
                return 1
              })
          )
      )
  )

  // /discordstatus - Check Discord integration status
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
          Component.yellow("Pending Messages: ").append(
            Component.white(pendingMessages.length + "")
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
