// Server Restart Command - Schedule server restarts with warnings
// Commands: /srestart <minutes> | /srestart cancel

// Track restart state
let restartScheduled = false
let restartCancelled = false
let restartId = 0
let restartTargetTick = 0

// Warning intervals in seconds (only applicable ones will be used)
const WARNING_INTERVALS = [
  { seconds: 600, message: '10 minutes' },
  { seconds: 300, message: '5 minutes' },
  { seconds: 120, message: '2 minutes' },
  { seconds: 60, message: '1 minute' },
  { seconds: 30, message: '30 seconds' },
  { seconds: 10, message: '10 seconds' },
  { seconds: 9, message: '9 seconds' },
  { seconds: 8, message: '8 seconds' },
  { seconds: 7, message: '7 seconds' },
  { seconds: 6, message: '6 seconds' },
  { seconds: 5, message: '5 seconds' },
  { seconds: 4, message: '4 seconds' },
  { seconds: 3, message: '3 seconds' },
  { seconds: 2, message: '2 seconds' },
  { seconds: 1, message: '1 second' }
]

// Broadcast message to all players and console
function broadcastMessage(server, component) {
  server.getPlayers().forEach(player => {
    player.sendSystemMessage(component)
  })
  server.sendSystemMessage(component)
}

// Build warning message component
function buildWarningMessage(timeText) {
  return Component.red('[Server] ').bold()
    .append(Component.yellow('Restarting in '))
    .append(Component.red(timeText).bold())
}

// Build countdown message (final 10 seconds)
function buildCountdownMessage(seconds) {
  return Component.red('[Server] ').bold()
    .append(Component.red(String(seconds)).bold())
}

// Schedule restart with all applicable warnings
function scheduleRestart(server, minutes, currentRestartId) {
  let totalSeconds = minutes * 60
  let totalTicks = totalSeconds * 20

  // Schedule each warning that applies
  WARNING_INTERVALS.forEach(warning => {
    if (warning.seconds <= totalSeconds) {
      let ticksUntilWarning = (totalSeconds - warning.seconds) * 20
      server.scheduleInTicks(ticksUntilWarning, () => {
        if (restartCancelled || restartId !== currentRestartId) return
        let msg = warning.seconds <= 10
          ? buildCountdownMessage(warning.seconds)
          : buildWarningMessage(warning.message)
        broadcastMessage(server, msg)
      })
    }
  })

  // Schedule the actual restart
  server.scheduleInTicks(totalTicks, () => {
    if (restartCancelled || restartId !== currentRestartId) return
    broadcastMessage(server, Component.red('[Server] ').bold().append(Component.red('Restarting now!').bold()))
    server.runCommandSilent('stop')
  })

  // Immediate announcement
  let msg = Component.green('[Server] ').bold()
    .append(Component.yellow('Server restart scheduled in '))
    .append(Component.green(minutes + (minutes === 1 ? ' minute' : ' minutes')).bold())
  broadcastMessage(server, msg)

  restartScheduled = true
  restartTargetTick = server.getTickCount() + totalTicks
  console.info('[Restart] Server restart scheduled in ' + minutes + ' minutes')
}

// Cancel scheduled restart
function cancelRestart(server) {
  if (!restartScheduled) {
    return false
  }

  restartCancelled = true
  restartScheduled = false
  restartTargetTick = 0

  let msg = Component.green('[Server] ').bold()
    .append(Component.yellow('Server restart has been '))
    .append(Component.green('cancelled').bold())
  broadcastMessage(server, msg)

  console.info('[Restart] Server restart cancelled')
  return true
}

ServerEvents.commandRegistry(event => {
  const { commands: Commands, arguments: Arguments } = event

  event.register(
    Commands.literal('srestart')
      .requires(src => src.hasPermission(2))
      .executes(ctx => {
        // Show help
        let src = ctx.source
        src.sendSystemMessage(Component.gold('=== Server Restart Commands ==='))
        src.sendSystemMessage(Component.yellow('/srestart <minutes>').append(Component.gray(' - Schedule restart')))
        src.sendSystemMessage(Component.yellow('/srestart cancel').append(Component.gray(' - Cancel scheduled restart')))
        src.sendSystemMessage(Component.yellow('/srestart info').append(Component.gray(' - Check restart status')))
        return 1
      })
      .then(
        Commands.literal('cancel')
          .executes(ctx => {
            let server = ctx.source.getServer()
            if (cancelRestart(server)) {
              return 1
            } else {
              ctx.source.sendSystemMessage(Component.red('No restart is currently scheduled.'))
              return 0
            }
          })
      )
      .then(
        Commands.literal('info')
          .executes(ctx => {
            let server = ctx.source.getServer()
            if (!restartScheduled) {
              ctx.source.sendSystemMessage(Component.yellow('No restart is currently scheduled.'))
              return 1
            }

            let ticksRemaining = restartTargetTick - server.getTickCount()
            if (ticksRemaining <= 0) {
              ctx.source.sendSystemMessage(Component.yellow('Restart is imminent.'))
              return 1
            }

            let secondsRemaining = Math.floor(ticksRemaining / 20)
            let minutes = Math.floor(secondsRemaining / 60)
            let seconds = secondsRemaining % 60

            let timeText
            if (minutes > 0) {
              timeText = minutes + (minutes === 1 ? ' minute' : ' minutes')
              if (seconds > 0) {
                timeText += ' ' + seconds + (seconds === 1 ? ' second' : ' seconds')
              }
            } else {
              timeText = seconds + (seconds === 1 ? ' second' : ' seconds')
            }

            ctx.source.sendSystemMessage(
              Component.gold('[Server] ').bold()
                .append(Component.yellow('Restart scheduled in '))
                .append(Component.red(timeText).bold())
            )
            return 1
          })
      )
      .then(
        Commands.argument('minutes', Arguments.INTEGER.create(event))
          .executes(ctx => {
            let minutes = Arguments.INTEGER.getResult(ctx, 'minutes')

            // Validate minimum
            if (minutes < 1) {
              ctx.source.sendSystemMessage(Component.red('Minutes must be at least 1.'))
              return 0
            }
            let server = ctx.source.getServer()

            // Cancel any existing restart
            if (restartScheduled) {
              restartCancelled = true
              restartScheduled = false
              ctx.source.sendSystemMessage(Component.yellow('Previous restart cancelled.'))
            }

            // Reset cancellation flag and increment restart ID
            restartCancelled = false
            restartId++

            scheduleRestart(server, minutes, restartId)
            return 1
          })
      )
  )
})
