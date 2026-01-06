ServerEvents.commandRegistry(event => {
  const { commands: Commands } = event

  const DISCORD_URL = "https://discord.gg/TYEtKS4GZt"

  function buildDiscordMessage() {
    const header = Component.gold("============== Vulpine Discord ==============")
    const footer = Component.gold("==========================================")

    const link = Component.aqua(DISCORD_URL)
      .underlined()
      .clickOpenUrl(DISCORD_URL)
      .hover(Component.yellow("Click to open Discord"))

    const middle = Component.white("Join our discord: ").append(link)

    // Join lines with newline between them
    return header
      .append("\n")
      .append(middle)
      .append("\n")
      .append(footer)
  }

  function replyToInvoker(ctx) {
    const msg = buildDiscordMessage()
    const player = ctx.source.player

    if (player) {
      // Only the player who ran the command
      player.tell(msg)
    } else {
      // Console / command block etc.
      ctx.source.sendSystemMessage(msg)
    }
    return 1
  }

  event.register(Commands.literal("dc").executes(ctx => replyToInvoker(ctx)))
  event.register(Commands.literal("discord").executes(ctx => replyToInvoker(ctx)))
})