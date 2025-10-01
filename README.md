# Discord Command Surface Bot

This project provides a Discord bot scaffold that mirrors a very large command
surface described in the accompanying specification. Only the prefix management
commands are fully functional; the remaining commands are generated from the
`command_spec.txt` file and currently respond with informative embeds that show
the intended usage and permission requirements. This makes it easy to flesh out
specific features later while immediately matching the documented command list.

## Running the bot

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Create a Discord bot application and copy its token.

3. Export the token before starting the bot:

   ```bash
   export DISCORD_TOKEN=your_token_here
   python bot.py
   ```

The bot will automatically create a `data/prefixes.json` file when you run it,
which persists guild and user specific prefixes.

## Extending functionality

Commands are defined in `command_spec.txt`. Each command follows the structure:

```
command name

Description text

arguments

argument description

permissions

permission description
```

Sub-commands are expressed by separating words in the command name with spaces.
Updating the specification file and restarting the bot will regenerate the
command hierarchy without further code changes.

To implement real functionality for a generated command, create a new cog and
register the desired command manually. The dynamically generated command can
then be removed from `command_spec.txt` to avoid duplicates.
