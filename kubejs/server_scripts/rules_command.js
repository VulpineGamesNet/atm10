ServerEvents.commandRegistry(event => {
  const { commands: Commands } = event

  function buildRulesMessage() {
    const header = Component.gold("==================== Rules ====================")
    const footer = Component.gold("===============================================")

    return header
      .append("\n").append(Component.yellow("1. ").bold()).append(Component.white("Intentionally lagging or crashing the server is prohibited"))
      .append("\n").append(Component.yellow("2. ").bold()).append(Component.white("Place multiblock machines within a single chunk"))
      .append("\n").append(Component.yellow("3. ").bold()).append(Component.white("English only in chat - so everyone can join the conversation"))
      .append("\n").append(Component.yellow("4. ").bold()).append(Component.white("No griefing - don't damage builds or harm players intentionally"))
      .append("\n").append(Component.yellow("5. ").bold()).append(Component.white("Be kind - no harassment, hate speech, or bullying"))
      .append("\n").append(Component.yellow("6. ").bold()).append(Component.white("No advertising other servers or communities"))
      .append("\n").append(Component.yellow("7. ").bold()).append(Component.white("Keep chat PG-13 - watch your language"))
      .append("\n").append(Component.yellow("8. ").bold()).append(Component.white("Laggy builds will receive a warning to optimize"))
      .append("\n").append(footer)
  }

  function replyToInvoker(ctx) {
    const msg = buildRulesMessage()
    const player = ctx.source.player

    if (player) {
      player.tell(msg)
    } else {
      ctx.source.sendSystemMessage(msg)
    }
    return 1
  }

  event.register(Commands.literal("rules").executes(ctx => replyToInvoker(ctx)))
})
