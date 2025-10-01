"""Discord bot scaffold that mirrors a comprehensive command surface."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping

import discord
from discord.ext import commands

DEFAULT_PREFIX = "!"
DATA_DIR = Path("data")
PREFIX_FILE = DATA_DIR / "prefixes.json"
SPEC_FILE = Path("command_spec.txt")


@dataclass
class CommandInfo:
    description: str
    arguments: str
    permissions: str


CommandTree = Dict[str, Any]

IGNORED_STANDALONE_LINES = {"Tier"}
KEYWORDS = {"arguments", "permissions"}


def ensure_storage() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not PREFIX_FILE.exists():
        PREFIX_FILE.write_text(json.dumps({"guild_prefixes": {}, "user_prefixes": {}}, indent=2))


def load_prefixes() -> MutableMapping[str, Dict[str, str]]:
    ensure_storage()
    with PREFIX_FILE.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_prefixes(data: Mapping[str, Dict[str, str]]) -> None:
    with PREFIX_FILE.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)


async def dynamic_prefix(bot: commands.Bot, message: discord.Message) -> Iterable[str]:
    if message.guild is None:
        return [DEFAULT_PREFIX]

    data = load_prefixes()
    user_prefix = data.get("user_prefixes", {}).get(str(message.author.id))
    guild_prefix = data.get("guild_prefixes", {}).get(str(message.guild.id))

    prefixes: List[str] = []
    if user_prefix:
        prefixes.append(user_prefix)
    if guild_prefix:
        prefixes.append(guild_prefix)
    if not prefixes:
        prefixes.append(DEFAULT_PREFIX)
    return prefixes


def parse_command_spec(path: Path) -> List[tuple[str, CommandInfo]]:
    if not path.exists():
        raise FileNotFoundError(f"Command specification file missing: {path}")

    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    entries: List[tuple[str, CommandInfo]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line or line in IGNORED_STANDALONE_LINES or line.lower() in KEYWORDS:
            i += 1
            continue

        name = line
        i += 1
        # description block
        desc_lines: List[str] = []
        while i < len(lines) and not lines[i]:
            i += 1
        while i < len(lines) and lines[i].lower() not in KEYWORDS:
            if lines[i] in IGNORED_STANDALONE_LINES:
                i += 1
                continue
            desc_lines.append(lines[i])
            i += 1
        description = " ".join(desc_lines).strip()

        if i >= len(lines) or lines[i].lower() != "arguments":
            raise ValueError(f"Expected 'arguments' after {name!r}")
        i += 1
        while i < len(lines) and not lines[i]:
            i += 1
        arg_lines: List[str] = []
        while i < len(lines) and lines[i].lower() not in KEYWORDS:
            arg_lines.append(lines[i])
            i += 1
        arguments = " ".join(arg_lines).strip() or "none"

        if i >= len(lines) or lines[i].lower() != "permissions":
            raise ValueError(f"Expected 'permissions' after {name!r}")
        i += 1
        while i < len(lines) and not lines[i]:
            i += 1
        perm_lines: List[str] = []
        while i < len(lines) and lines[i] and lines[i].lower() not in KEYWORDS:
            perm_lines.append(lines[i])
            i += 1
        permissions = " ".join(perm_lines).strip() or "none"

        entries.append((name, CommandInfo(description, arguments, permissions)))
    return entries


def build_command_tree(entries: List[tuple[str, CommandInfo]]) -> CommandTree:
    tree: CommandTree = {}
    for path, info in entries:
        parts = path.split()
        node: CommandTree = tree
        for index, part in enumerate(parts):
            is_last = index == len(parts) - 1
            if is_last:
                existing = node.get(part)
                if isinstance(existing, dict):
                    existing["_info"] = info
                else:
                    node[part] = info
            else:
                existing = node.get(part)
                if isinstance(existing, CommandInfo):
                    new_node: CommandTree = {"_info": existing}
                    node[part] = new_node
                    node = new_node
                elif isinstance(existing, dict):
                    node = existing
                else:
                    new_node = {}
                    node[part] = new_node
                    node = new_node
    return tree


def add_info_command(target: commands.Group | commands.Bot, name: str, info: CommandInfo, qualified_name: str) -> None:
    async def callback(ctx: commands.Context, *args: str) -> None:
        embed = discord.Embed(title=f"/{qualified_name}")
        embed.add_field(name="Description", value=info.description or "No description provided.", inline=False)
        embed.add_field(name="Arguments", value=info.arguments or "None", inline=False)
        embed.add_field(name="Required Permissions", value=info.permissions or "None", inline=False)
        if args:
            embed.add_field(name="Provided Arguments", value=", ".join(args), inline=False)
        await ctx.send(embed=embed)

    command = commands.Command(callback, name=name, help=info.description)
    target.add_command(command)


def build_group(name: str, definition: Mapping[str, Any], parent_name: str | None = None) -> commands.Group:
    qualified = f"{parent_name} {name}".strip() if parent_name else name
    info = definition.get("_info")
    group = commands.Group(name=name, invoke_without_command=True)

    if isinstance(info, CommandInfo):
        async def default(ctx: commands.Context, *args: str) -> None:
            embed = discord.Embed(title=f"/{ctx.command.qualified_name}")
            embed.add_field(name="Description", value=info.description or "No description provided.", inline=False)
            embed.add_field(name="Arguments", value=info.arguments or "None", inline=False)
            embed.add_field(name="Required Permissions", value=info.permissions or "None", inline=False)
            if args:
                embed.add_field(name="Provided Arguments", value=", ".join(args), inline=False)
            await ctx.send(embed=embed)

        group.callback = default  # type: ignore[assignment]

    for child_name, child_definition in definition.items():
        if child_name == "_info":
            continue
        if isinstance(child_definition, CommandInfo):
            add_info_command(group, child_name, child_definition, f"{qualified} {child_name}".strip())
        elif isinstance(child_definition, Mapping):
            group.add_command(build_group(child_name, child_definition, qualified))
        else:
            raise TypeError(f"Unexpected definition type for {child_name!r}")

    return group


def register_generated_commands(bot: commands.Bot, tree: CommandTree) -> None:
    for name, definition in tree.items():
        if isinstance(definition, CommandInfo):
            add_info_command(bot, name, definition, name)
        elif isinstance(definition, Mapping):
            bot.add_command(build_group(name, definition))
        else:
            raise TypeError(f"Unexpected definition type for {name!r}")


class PrefixCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.group(name="prefix", invoke_without_command=True)
    async def prefix(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            await ctx.send(f"My default prefix is `{DEFAULT_PREFIX}`.")
            return

        data = load_prefixes()
        guild_prefix = data.get("guild_prefixes", {}).get(str(ctx.guild.id))
        user_prefix = data.get("user_prefixes", {}).get(str(ctx.author.id))

        lines = [f"Default prefix: `{DEFAULT_PREFIX}`"]
        if guild_prefix:
            lines.append(f"Guild prefix: `{guild_prefix}`")
        if user_prefix:
            lines.append(f"Your personal prefix: `{user_prefix}`")

        await ctx.send("\n".join(lines))

    @prefix.command(name="self")
    async def prefix_self(self, ctx: commands.Context, *, new_prefix: str) -> None:
        data = load_prefixes()
        data.setdefault("user_prefixes", {})[str(ctx.author.id)] = new_prefix
        save_prefixes(data)
        await ctx.send(f"Your personal prefix has been set to `{new_prefix}`.")

    @prefix.command(name="remove")
    @commands.has_guild_permissions(administrator=True)
    async def prefix_remove(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            await ctx.send("This command can only be used in a guild.")
            return

        data = load_prefixes()
        removed = data.get("guild_prefixes", {}).pop(str(ctx.guild.id), None)
        save_prefixes(data)

        if removed:
            await ctx.send("Guild prefix removed. Falling back to default prefix.")
        else:
            await ctx.send("No guild prefix was set.")

    @prefix.command(name="set")
    @commands.has_guild_permissions(administrator=True)
    async def prefix_set(self, ctx: commands.Context, *, new_prefix: str) -> None:
        if ctx.guild is None:
            await ctx.send("This command can only be used in a guild.")
            return

        data = load_prefixes()
        data.setdefault("guild_prefixes", {})[str(ctx.guild.id)] = new_prefix
        save_prefixes(data)
        await ctx.send(f"Guild prefix has been set to `{new_prefix}`.")


def create_bot() -> commands.Bot:
    intents = discord.Intents.default()
    intents.message_content = True

    bot = commands.Bot(command_prefix=dynamic_prefix, intents=intents)
    bot.add_cog(PrefixCog(bot))

    entries = parse_command_spec(SPEC_FILE)
    tree = build_command_tree(entries)
    register_generated_commands(bot, tree)

    @bot.event
    async def on_ready() -> None:
        print(f"Logged in as {bot.user} (ID: {bot.user.id})")

    return bot


def main() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN environment variable is required.")

    bot = create_bot()
    bot.run(token)


if __name__ == "__main__":
    main()
