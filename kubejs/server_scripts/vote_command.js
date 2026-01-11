// KubeVote - Voting System with Rewards, Streaks, and Leaderboard
// Integrates with external Votifier service via /kubevote process command

// ============================================================================
// CONFIGURATION
// ============================================================================

const VOTE_ROOT_KEY = "kubevote"

// Voting sites configuration
// id: must match the service name sent by voting sites
// cooldown: display cooldown in milliseconds (86400000 = 24 hours) - for UI only
const VOTING_SITES = [
  {
    id: "moddedminecraftservers.com",
    name: "Modded MC Servers",
    url: "https://moddedminecraftservers.com/server/vulpine-all-the-mods-10.60869/",
    cooldown: 86400000
  },
  {
    id: "minecraftservers.org",
    name: "Minecraft Servers",
    url: "https://minecraftservers.org/server/681945",
    cooldown: 86400000
  },
  {
    id: "minecraft-mp.com",
    name: "Minecraft MP",
    url: "https://minecraft-mp.com/server-s352488",
    cooldown: 86400000
  },
  {
    id: "planetminecraft.com",
    name: "Planet Minecraft",
    url: "https://www.planetminecraft.com/server/vulpine-atm10/",
    cooldown: 86400000
  },
  {
    id: "minecraft-server-list.com",
    name: "MC Server List",
    url: "https://minecraft-server-list.com/server/516945/",
    cooldown: 86400000
  },
  {
    id: "topg.org",
    name: "TopG",
    url: "https://topg.org/minecraft-servers/server-678506",
    cooldown: 86400000
  },
  {
    id: "minestatus.net_test_vote",
    name: "MineStatus Test",
    url: "https://minestatus.net/",
    cooldown: 86400000
  }
]

// Reward configuration - Physical coins (gold_nugget with custom_model_data)
// Base reward is 1x $100 coin, streak multipliers add more coins
// Half multipliers (1.5x, 2.5x) give $100 + $50 coins
const STREAK_BONUSES = [
  { days: 3, multiplier: 1.5, name: "3-day streak" },    // 1x $100 + 1x $50 = $150
  { days: 7, multiplier: 2.0, name: "Weekly streak" },   // 2x $100 = $200
  { days: 14, multiplier: 2.5, name: "2-week streak" },  // 2x $100 + 1x $50 = $250
  { days: 30, multiplier: 3.0, name: "Monthly streak" }  // 3x $100 = $300
]

// Coin item configurations
const COIN_100 = {
  id: "minecraft:gold_nugget",
  customModelData: 719100,
  value: 100,
  name: '{"text":"Coin","color":"blue","italic":false}',
  lore: '{"text":"Worth $100","color":"gray","italic":false}'
}

const COIN_50 = {
  id: "minecraft:gold_nugget",
  customModelData: 719050,
  value: 50,
  name: '{"text":"Coin","color":"green","italic":false}',
  lore: '{"text":"Worth $50","color":"gray","italic":false}'
}

// ============================================================================
// DATA MANAGEMENT
// ============================================================================

let voteDataCache = {}
let leaderboardCache = { month: "", votes: {} }
let dataLoaded = false
let claimQueue = []  // Queue for pending claim requests

function getRootNbt(server) {
  if (!server.persistentData.contains(VOTE_ROOT_KEY)) {
    server.persistentData.put(VOTE_ROOT_KEY, NBT.compoundTag())
  }
  return server.persistentData.getCompound(VOTE_ROOT_KEY)
}

function ensureDataLoaded(server) {
  if (dataLoaded) return

  console.info("[KubeVote] Loading data...")
  loadVoteData(server)
  loadLeaderboard(server)
  dataLoaded = true
}

function loadVoteData(server) {
  let rootNbt = getRootNbt(server)

  if (!rootNbt.contains("players")) {
    rootNbt.put("players", NBT.compoundTag())
  }

  voteDataCache = {}
  let playersNbt = rootNbt.getCompound("players")
  let keys = playersNbt.getAllKeys().toArray()

  for (let i = 0; i < keys.length; i++) {
    let uuid = keys[i]
    let playerNbt = playersNbt.getCompound(uuid)

    let lastVotes = {}
    if (playerNbt.contains("lastVotes")) {
      let lastVotesNbt = playerNbt.getCompound("lastVotes")
      let siteKeys = lastVotesNbt.getAllKeys().toArray()
      for (let j = 0; j < siteKeys.length; j++) {
        lastVotes[siteKeys[j]] = lastVotesNbt.getLong(siteKeys[j])
      }
    }

    voteDataCache[uuid] = {
      lastVotes: lastVotes,
      streak: {
        count: playerNbt.contains("streakCount") ? playerNbt.getInt("streakCount") : 0,
        lastDate: playerNbt.contains("streakLastDate") ? playerNbt.getString("streakLastDate") : ""
      },
      totalVotes: playerNbt.contains("totalVotes") ? playerNbt.getInt("totalVotes") : 0
    }
  }

  console.info("[KubeVote] Loaded vote data for " + keys.length + " players")
}

function savePlayerVoteData(server, uuid) {
  let rootNbt = getRootNbt(server)
  if (!rootNbt.contains("players")) {
    rootNbt.put("players", NBT.compoundTag())
  }

  let playersNbt = rootNbt.getCompound("players")
  let playerNbt = NBT.compoundTag()
  let data = voteDataCache[uuid]

  if (!data) return

  // Save lastVotes (for display purposes)
  let lastVotesNbt = NBT.compoundTag()
  for (let siteId in data.lastVotes) {
    lastVotesNbt.putLong(siteId, data.lastVotes[siteId])
  }
  playerNbt.put("lastVotes", lastVotesNbt)

  // Save streak
  playerNbt.putInt("streakCount", data.streak.count)
  playerNbt.putString("streakLastDate", data.streak.lastDate)

  // Save total
  playerNbt.putInt("totalVotes", data.totalVotes)

  playersNbt.put(uuid, playerNbt)
}

function loadLeaderboard(server) {
  let rootNbt = getRootNbt(server)

  if (!rootNbt.contains("leaderboard")) {
    rootNbt.put("leaderboard", NBT.compoundTag())
  }

  let lbNbt = rootNbt.getCompound("leaderboard")
  leaderboardCache = {
    month: lbNbt.contains("month") ? lbNbt.getString("month") : "",
    votes: {}
  }

  if (lbNbt.contains("votes")) {
    let votesNbt = lbNbt.getCompound("votes")
    let keys = votesNbt.getAllKeys().toArray()
    for (let i = 0; i < keys.length; i++) {
      leaderboardCache.votes[keys[i]] = votesNbt.getInt(keys[i])
    }
  }
}

function saveLeaderboard(server) {
  let rootNbt = getRootNbt(server)
  let lbNbt = NBT.compoundTag()

  lbNbt.putString("month", leaderboardCache.month)

  let votesNbt = NBT.compoundTag()
  for (let uuid in leaderboardCache.votes) {
    votesNbt.putInt(uuid, leaderboardCache.votes[uuid])
  }
  lbNbt.put("votes", votesNbt)

  rootNbt.put("leaderboard", lbNbt)
}

function ensurePlayerData(uuid) {
  if (!voteDataCache[uuid]) {
    voteDataCache[uuid] = {
      lastVotes: {},
      streak: { count: 0, lastDate: "" },
      totalVotes: 0
    }
  }
  return voteDataCache[uuid]
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

function getCurrentDateString() {
  let now = new Date()
  let year = now.getFullYear()
  let month = (now.getMonth() + 1).toString().padStart(2, "0")
  let day = now.getDate().toString().padStart(2, "0")
  return year + "-" + month + "-" + day
}

function getCurrentMonthString() {
  let now = new Date()
  let year = now.getFullYear()
  let month = (now.getMonth() + 1).toString().padStart(2, "0")
  return year + "-" + month
}

function getYesterdayDateString() {
  let now = new Date()
  now.setDate(now.getDate() - 1)
  let year = now.getFullYear()
  let month = (now.getMonth() + 1).toString().padStart(2, "0")
  let day = now.getDate().toString().padStart(2, "0")
  return year + "-" + month + "-" + day
}

function formatTimeRemaining(ms) {
  if (ms <= 0) return "Ready!"

  let hours = Math.floor(ms / 3600000)
  let minutes = Math.floor((ms % 3600000) / 60000)

  if (hours > 0) {
    return hours + "h " + minutes + "m"
  }
  return minutes + "m"
}

function getSiteById(siteId) {
  for (let i = 0; i < VOTING_SITES.length; i++) {
    if (VOTING_SITES[i].id.toLowerCase() === siteId.toLowerCase()) {
      return VOTING_SITES[i]
    }
  }
  return null
}

function getStreakMultiplier(streakCount) {
  let multiplier = 1.0
  let bonusName = null

  for (let i = STREAK_BONUSES.length - 1; i >= 0; i--) {
    if (streakCount >= STREAK_BONUSES[i].days) {
      multiplier = STREAK_BONUSES[i].multiplier
      bonusName = STREAK_BONUSES[i].name
      break
    }
  }

  return { multiplier: multiplier, name: bonusName }
}

function createCoinItem(coinConfig, count) {
  // Use 1.21 component syntax
  let itemString = coinConfig.id + '[' +
    'minecraft:custom_model_data=' + coinConfig.customModelData + ',' +
    'minecraft:custom_name=\'' + coinConfig.name + '\',' +
    'minecraft:lore=[\'' + coinConfig.lore + '\']' +
    ']'
  return Item.of(itemString).withCount(count)
}

function calculateCoinReward(multiplier) {
  // Base is 1x $100 coin = $100
  // Multiplier determines total value: 1.0 = $100, 1.5 = $150, 2.0 = $200, etc.
  let totalValue = Math.round(100 * multiplier)

  // Calculate how many $100 coins and $50 coins to give
  let coins100 = Math.floor(totalValue / 100)
  let remainder = totalValue % 100

  // If remainder is 50 or more, give a $50 coin
  let coins50 = remainder >= 50 ? 1 : 0

  return {
    coins100: coins100,
    coins50: coins50,
    totalValue: (coins100 * 100) + (coins50 * 50)
  }
}

function giveCoinsToPlayer(player, coins100, coins50) {
  if (coins100 > 0) {
    let item100 = createCoinItem(COIN_100, coins100)
    player.give(item100)
  }
  if (coins50 > 0) {
    let item50 = createCoinItem(COIN_50, coins50)
    player.give(item50)
  }
  // Play reward sound
  playRewardSound(player)
}

function playRewardSound(player) {
  // Play a sparkly/sprinkling sound effect using playsound command
  player.server.runCommandSilent("playsound minecraft:block.amethyst_block.chime player " + player.getName().getString() + " ~ ~ ~ 1.0 1.0")
  // Add a second sound for more sparkle effect
  player.server.scheduleInTicks(3, () => {
    player.server.runCommandSilent("playsound minecraft:entity.experience_orb.pickup player " + player.getName().getString() + " ~ ~ ~ 0.5 1.2")
  })
}

function formatCoinReward(coins100, coins50) {
  let parts = []
  if (coins100 > 0) {
    parts.push(coins100 + "x $100")
  }
  if (coins50 > 0) {
    parts.push(coins50 + "x $50")
  }
  return parts.join(" + ")
}

// ============================================================================
// VOTE PROCESSING
// ============================================================================

function processVote(server, username, serviceId) {
  ensureDataLoaded(server)

  // Find player by username
  let player = server.getPlayer(username)
  if (!player) {
    // Player offline - votifier service will save as pending reward
    console.info("[KubeVote] Player " + username + " is offline, vote saved as pending")
    return { success: false, message: "Player not found" }
  }

  let uuid = player.getStringUuid()
  let playerName = player.getName().getString()

  let site = getSiteById(serviceId)
  if (!site) {
    console.warn("[KubeVote] Unknown voting site: " + serviceId)
    // Still process the vote even if site is unknown
    site = { id: serviceId, name: serviceId, cooldown: 86400000 }
  }

  let data = ensurePlayerData(uuid)
  let today = getCurrentDateString()
  let yesterday = getYesterdayDateString()
  let currentMonth = getCurrentMonthString()

  // Update last vote time (for display purposes only)
  data.lastVotes[site.id] = Date.now()

  // Update streak
  if (data.streak.lastDate === yesterday) {
    data.streak.count++
  } else if (data.streak.lastDate !== today) {
    data.streak.count = 1
  }
  data.streak.lastDate = today

  // Update totals
  data.totalVotes++

  // Update leaderboard
  if (leaderboardCache.month !== currentMonth) {
    // New month, reset leaderboard
    leaderboardCache = { month: currentMonth, votes: {} }
    console.info("[KubeVote] New month - leaderboard reset")
  }
  leaderboardCache.votes[uuid] = (leaderboardCache.votes[uuid] || 0) + 1

  // Calculate reward - $100 and $50 coins based on streak multiplier
  let streakInfo = getStreakMultiplier(data.streak.count)
  let coinReward = calculateCoinReward(streakInfo.multiplier)

  // Save data
  savePlayerVoteData(server, uuid)
  saveLeaderboard(server)

  // Give reward - physical coins
  giveCoinsToPlayer(player, coinReward.coins100, coinReward.coins50)

  // Notify player
  player.tell(Component.gold("★ ").append(Component.yellow("Vote Reward")).append(Component.gold(" ★")))
  player.tell(
    Component.gray("  Thanks for voting on ")
      .append(Component.aqua(site.name))
      .append(Component.gray("!"))
  )

  // Reward breakdown
  let rewardMsg = Component.gray("  You received: ")
  if (coinReward.coins100 > 0) {
    rewardMsg.append(Component.blue(coinReward.coins100 + "x "))
      .append(Component.gold("$100 Coin"))
  }
  if (coinReward.coins100 > 0 && coinReward.coins50 > 0) {
    rewardMsg.append(Component.gray(" + "))
  }
  if (coinReward.coins50 > 0) {
    rewardMsg.append(Component.green(coinReward.coins50 + "x "))
      .append(Component.darkGreen("$50 Coin"))
  }
  player.tell(rewardMsg)

  player.tell(
    Component.gray("  Total: ")
      .append(Component.green("$" + coinReward.totalValue))
  )

  // Streak info
  let streakLine = Component.gray("  Streak: ")
    .append(Component.yellow(data.streak.count + " day" + (data.streak.count !== 1 ? "s" : "")))
  if (streakInfo.name) {
    streakLine.append(Component.gray(" ("))
      .append(Component.aqua(streakInfo.name))
      .append(Component.gray(")"))
  }
  player.tell(streakLine)

  player.tell(
    Component.gray("  Lifetime votes: ")
      .append(Component.yellow(data.totalVotes.toString()))
  )

  let coinDisplay = formatCoinReward(coinReward.coins100, coinReward.coins50)
  console.info("[KubeVote] Processed vote from " + playerName + " for " + site.name + " - reward: " + coinDisplay + " ($" + coinReward.totalValue + ") (streak: " + data.streak.count + ")")

  return { success: true, coins100: coinReward.coins100, coins50: coinReward.coins50, value: coinReward.totalValue, streak: data.streak.count }
}

// ============================================================================
// SERVER EVENTS
// ============================================================================

ServerEvents.loaded(event => {
  dataLoaded = false
  voteDataCache = {}
  leaderboardCache = { month: "", votes: {} }
  ensureDataLoaded(event.server)
  console.info("[KubeVote] Vote system loaded")
})

// ============================================================================
// COMMANDS
// ============================================================================

ServerEvents.commandRegistry(event => {
  let Commands = event.getCommands()
  let Arguments = event.getArguments()

  // /vote - Show voting sites list
  event.register(
    Commands.literal("vote")
      .executes(ctx => {
        let src = ctx.getSource()
        let player = src.getPlayer()

        if (!player) {
          src.sendFailure(Component.red("This command can only be used by players"))
          return 0
        }

        let server = src.getServer()
        ensureDataLoaded(server)

        let uuid = player.getStringUuid()
        let data = ensurePlayerData(uuid)
        let now = Date.now()

        src.sendSystemMessage(Component.gold("============ Vote for Rewards! ============"))

        // Show each voting site with cooldown status
        for (let i = 0; i < VOTING_SITES.length; i++) {
          let site = VOTING_SITES[i]
          let lastVote = data.lastVotes[site.id] || 0
          let timeUntilReady = site.cooldown - (now - lastVote)

          let siteMsg = Component.empty()

          if (timeUntilReady <= 0) {
            // Ready to vote - green with clickable link
            siteMsg.append(Component.green("✓ "))
              .append(
                Component.green(site.name)
                  .underlined()
                  .clickOpenUrl(site.url)
                  .hover(Component.yellow("Click to vote!"))
              )
          } else {
            // On cooldown - red with time remaining
            siteMsg.append(Component.red("✗ "))
              .append(Component.gray(site.name))
              .append(Component.red(" (" + formatTimeRemaining(timeUntilReady) + ")"))
          }

          src.sendSystemMessage(siteMsg)
        }

        // Show streak and reward info
        let streakInfo = getStreakMultiplier(data.streak.count)
        let coinReward = calculateCoinReward(streakInfo.multiplier)

        src.sendSystemMessage(Component.gold("=========================================="))

        // Streak info
        let streakLine = Component.gray("Streak: ")
          .append(Component.yellow(data.streak.count + " day" + (data.streak.count !== 1 ? "s" : "")))

        if (streakInfo.name) {
          streakLine.append(Component.gray(" ("))
            .append(Component.aqua(streakInfo.name))
            .append(Component.gray(")"))
        }
        src.sendSystemMessage(streakLine)

        // Your next reward
        let rewardLine = Component.gray("Next reward: ")
        if (coinReward.coins100 > 0) {
          rewardLine.append(Component.blue(coinReward.coins100 + "x "))
            .append(Component.gold("$100"))
        }
        if (coinReward.coins100 > 0 && coinReward.coins50 > 0) {
          rewardLine.append(Component.gray(" + "))
        }
        if (coinReward.coins50 > 0) {
          rewardLine.append(Component.green(coinReward.coins50 + "x "))
            .append(Component.darkGreen("$50"))
        }
        rewardLine.append(Component.gray(" = "))
          .append(Component.green("$" + coinReward.totalValue))
        src.sendSystemMessage(rewardLine)

        return 1
      })

      // /vote list - Alias for /vote
      .then(Commands.literal("list")
        .executes(ctx => {
          // Just run the parent command
          return ctx.getSource().getServer().getCommands().getDispatcher()
            .execute("vote", ctx.getSource())
        })
      )

      // /vote stats [player] - Show vote statistics
      .then(Commands.literal("stats")
        .executes(ctx => {
          let player = ctx.getSource().getPlayer()
          if (!player) {
            ctx.getSource().sendFailure(Component.red("This command can only be used by players"))
            return 0
          }

          return showVoteStats(ctx.getSource(), player.getStringUuid(), player.getName().getString())
        })
        .then(
          Commands.argument("player", Arguments.GAME_PROFILE.create(event))
            .requires(src => src.hasPermission(2))
            .executes(ctx => {
              let profiles = Arguments.GAME_PROFILE.getResult(ctx, "player")
              let profileArray = profiles.toArray()

              if (profileArray.length === 0) {
                ctx.getSource().sendFailure(Component.red("Player not found"))
                return 0
              }

              let profile = profileArray[0]
              return showVoteStats(ctx.getSource(), profile.getId().toString(), profile.getName())
            })
        )
      )

      // /vote top - Show leaderboard
      .then(Commands.literal("top")
        .executes(ctx => {
          let src = ctx.getSource()
          let server = src.getServer()
          ensureDataLoaded(server)

          let currentMonth = getCurrentMonthString()

          src.sendSystemMessage(Component.gold("========== Vote Leaderboard (" + currentMonth + ") =========="))

          if (leaderboardCache.month !== currentMonth || Object.keys(leaderboardCache.votes).length === 0) {
            src.sendSystemMessage(Component.gray("No votes recorded this month yet!"))
            return 1
          }

          // Sort by vote count
          let sorted = []
          for (let uuid in leaderboardCache.votes) {
            sorted.push({ uuid: uuid, votes: leaderboardCache.votes[uuid] })
          }
          sorted.sort(function(a, b) { return b.votes - a.votes })

          // Show top 10
          let toShow = Math.min(sorted.length, 10)
          for (let i = 0; i < toShow; i++) {
            let entry = sorted[i]
            let playerName = "Unknown"

            // Try to get player name
            let onlinePlayer = server.getPlayer(entry.uuid)
            if (onlinePlayer) {
              playerName = onlinePlayer.getName().getString()
            } else {
              try {
                let profileCache = server.getProfileCache()
                if (profileCache) {
                  let optProfile = profileCache.get(Java.loadClass('java.util.UUID').fromString(entry.uuid))
                  if (optProfile && optProfile.isPresent()) {
                    playerName = optProfile.get().getName()
                  }
                }
              } catch (e) {
                playerName = entry.uuid.substring(0, 8) + "..."
              }
            }

            let rankColor = i === 0 ? Component.gold : (i === 1 ? Component.gray : (i === 2 ? Component.darkRed : Component.white))
            let msg = Component.empty()
              .append(rankColor("#" + (i + 1) + " "))
              .append(Component.yellow(playerName))
              .append(Component.gray(" - "))
              .append(Component.green(entry.votes + " vote" + (entry.votes !== 1 ? "s" : "")))

            src.sendSystemMessage(msg)
          }

          return 1
        })
      )

      // /vote claim - Request pending rewards (votifier service handles actual claim)
      .then(Commands.literal("claim")
        .executes(ctx => {
          let src = ctx.getSource()
          let player = src.getPlayer()

          if (!player) {
            src.sendFailure(Component.red("This command can only be used by players"))
            return 0
          }

          let username = player.getName().getString()
          // Add to claim queue for votifier service to poll
          if (claimQueue.indexOf(username) === -1) {
            claimQueue.push(username)
          }
          ctx.getSource().sendSystemMessage(Component.gray("Checking for pending rewards..."))

          return 1
        })
      )
  )

  // /kubevote - Internal commands for Votifier service
  event.register(
    Commands.literal("kubevote")
      .requires(src => src.hasPermission(2))

      // /kubevote claimqueue - Get and clear pending claim requests (polled by votifier)
      .then(Commands.literal("claimqueue")
        .executes(ctx => {
          if (claimQueue.length === 0) {
            ctx.getSource().sendSystemMessage(Component.literal("CLAIMQUEUE:"))
            return 1
          }
          // Return queue as comma-separated list and clear it
          let result = claimQueue.join(",")
          claimQueue = []
          ctx.getSource().sendSystemMessage(Component.literal("CLAIMQUEUE:" + result))
          return 1
        })
      )

      // /kubevote claim <player> <count> - Give pending rewards (called by votifier service)
      .then(Commands.literal("claim")
        .then(
          Commands.argument("player", Arguments.STRING.create(event))
            .then(
              Commands.argument("count", Arguments.INTEGER.create(event))
                .executes(ctx => {
                  let playerName = Arguments.STRING.getResult(ctx, "player")
                  let count = Arguments.INTEGER.getResult(ctx, "count")
                  let server = ctx.getSource().getServer()

                  let player = server.getPlayer(playerName)
                  if (!player) {
                    ctx.getSource().sendSystemMessage(Component.red("Player " + playerName + " not found or offline"))
                    return 0
                  }

                  if (count <= 0) {
                    player.tell(Component.yellow("You have no pending vote rewards."))
                    return 1
                  }

                  // Calculate rewards (base reward per pending vote)
                  let totalCoins100 = 0
                  let totalCoins50 = 0
                  for (let i = 0; i < count; i++) {
                    let coinReward = calculateCoinReward(1.0)
                    totalCoins100 += coinReward.coins100
                    totalCoins50 += coinReward.coins50
                  }

                  // Give the coins
                  giveCoinsToPlayer(player, totalCoins100, totalCoins50)

                  // Notify player
                  let totalValue = (totalCoins100 * 100) + (totalCoins50 * 50)
                  player.tell(Component.gold("★ ").append(Component.yellow("Pending Rewards Claimed")).append(Component.gold(" ★")))
                  player.tell(
                    Component.gray("  Claimed ")
                      .append(Component.green(count.toString()))
                      .append(Component.gray(" pending vote reward" + (count !== 1 ? "s" : "") + "!"))
                  )

                  let rewardMsg = Component.gray("  You received: ")
                  if (totalCoins100 > 0) {
                    rewardMsg.append(Component.blue(totalCoins100 + "x "))
                      .append(Component.gold("$100 Coin"))
                  }
                  if (totalCoins100 > 0 && totalCoins50 > 0) {
                    rewardMsg.append(Component.gray(" + "))
                  }
                  if (totalCoins50 > 0) {
                    rewardMsg.append(Component.green(totalCoins50 + "x "))
                      .append(Component.darkGreen("$50 Coin"))
                  }
                  player.tell(rewardMsg)
                  player.tell(
                    Component.gray("  Total: ")
                      .append(Component.green("$" + totalValue))
                  )

                  console.info("[KubeVote] " + playerName + " claimed " + count + " pending rewards ($" + totalValue + ")")
                  ctx.getSource().sendSystemMessage(Component.green("Gave " + count + " pending rewards to " + playerName))

                  return 1
                })
            )
        )
      )

      // /kubevote process <player> <service> - Process incoming vote
      .then(Commands.literal("process")
        .then(
          Commands.argument("player", Arguments.STRING.create(event))
            .then(
              Commands.argument("service", Arguments.STRING.create(event))
                .executes(ctx => {
                  let playerName = Arguments.STRING.getResult(ctx, "player")
                  let serviceId = Arguments.STRING.getResult(ctx, "service")
                  let server = ctx.getSource().getServer()

                  let result = processVote(server, playerName, serviceId)

                  if (result.success) {
                    let coinDisplay = formatCoinReward(result.coins100, result.coins50)
                    ctx.getSource().sendSystemMessage(
                      Component.green("Vote processed for " + playerName + " from " + serviceId + " - reward: " + coinDisplay + " ($" + result.value + ")")
                    )
                  } else {
                    ctx.getSource().sendSystemMessage(
                      Component.yellow("Vote not processed for " + playerName + ": " + result.message)
                    )
                  }

                  return result.success ? 1 : 0
                })
            )
        )
      )

      // /kubevote admin - Admin subcommands
      .then(Commands.literal("admin")
        .executes(ctx => {
          ctx.getSource().sendSystemMessage(Component.gold("=== KubeVote Admin Commands ==="))
          ctx.getSource().sendSystemMessage(Component.yellow("/kubevote admin reset <player>").append(Component.gray(" - Reset player vote data")))
          ctx.getSource().sendSystemMessage(Component.yellow("/kubevote admin reload").append(Component.gray(" - Reload vote data")))
          return 1
        })

        // /kubevote admin reset <player>
        .then(Commands.literal("reset")
          .then(
            Commands.argument("player", Arguments.GAME_PROFILE.create(event))
              .executes(ctx => {
                let profiles = Arguments.GAME_PROFILE.getResult(ctx, "player")
                let profileArray = profiles.toArray()

                if (profileArray.length === 0) {
                  ctx.getSource().sendFailure(Component.red("Player not found"))
                  return 0
                }

                let server = ctx.getSource().getServer()
                let profile = profileArray[0]
                let uuid = profile.getId().toString()
                let playerName = profile.getName()

                ensureDataLoaded(server)

                // Reset player data
                delete voteDataCache[uuid]
                delete leaderboardCache.votes[uuid]

                // Remove from NBT
                let rootNbt = getRootNbt(server)
                if (rootNbt.contains("players")) {
                  rootNbt.getCompound("players").remove(uuid)
                }
                saveLeaderboard(server)

                ctx.getSource().sendSystemMessage(
                  Component.green("Reset vote data for " + playerName)
                )

                return 1
              })
          )
        )

        // /kubevote admin reload
        .then(Commands.literal("reload")
          .executes(ctx => {
            let server = ctx.getSource().getServer()
            dataLoaded = false
            ensureDataLoaded(server)
            ctx.getSource().sendSystemMessage(Component.green("Vote data reloaded"))
            return 1
          })
        )
      )
  )

  // Helper function to show vote stats
  function showVoteStats(src, uuid, playerName) {
    let server = src.getServer()
    ensureDataLoaded(server)

    let data = voteDataCache[uuid]
    if (!data) {
      src.sendSystemMessage(Component.gray("No vote data found for " + playerName))
      return 1
    }

    src.sendSystemMessage(Component.gold("========== Vote Stats: " + playerName + " =========="))

    // Total votes
    src.sendSystemMessage(
      Component.empty()
        .append(Component.gray("Total Votes: "))
        .append(Component.yellow(data.totalVotes.toString()))
    )

    // Streak
    let streakInfo = getStreakMultiplier(data.streak.count)
    src.sendSystemMessage(
      Component.empty()
        .append(Component.gray("Current Streak: "))
        .append(Component.yellow(data.streak.count + " day" + (data.streak.count !== 1 ? "s" : "")))
        .append(streakInfo.name ? Component.aqua(" (" + streakInfo.name + ")") : Component.empty())
    )

    // Multiplier
    src.sendSystemMessage(
      Component.empty()
        .append(Component.gray("Reward Multiplier: "))
        .append(Component.green("x" + streakInfo.multiplier))
    )

    // Monthly votes
    let monthlyVotes = leaderboardCache.votes[uuid] || 0
    src.sendSystemMessage(
      Component.empty()
        .append(Component.gray("This Month: "))
        .append(Component.yellow(monthlyVotes + " vote" + (monthlyVotes !== 1 ? "s" : "")))
    )

    // Per-site cooldowns
    let now = Date.now()
    src.sendSystemMessage(Component.gray("--- Site Cooldowns ---"))
    for (let i = 0; i < VOTING_SITES.length; i++) {
      let site = VOTING_SITES[i]
      let lastVote = data.lastVotes[site.id] || 0
      let timeUntilReady = site.cooldown - (now - lastVote)

      let siteMsg = Component.empty()
        .append(Component.gray(site.name + ": "))

      if (timeUntilReady <= 0) {
        siteMsg.append(Component.green("Ready"))
      } else {
        siteMsg.append(Component.red(formatTimeRemaining(timeUntilReady)))
      }

      src.sendSystemMessage(siteMsg)
    }

    return 1
  }
})

console.info("[KubeVote] Vote command system loaded")
