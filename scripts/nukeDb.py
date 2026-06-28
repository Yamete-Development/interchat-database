# Copyright (c) 2026 Oxara Development
# All rights reserved.
#
# This source code and any related materials are the confidential and
# proprietary information of Oxara Development.
#
# Unauthorized copying, modification, distribution, use, or disclosure
# of this software, in whole or in part, is strictly prohibited without
# prior written permission from Oxara Development.
#
# Use is restricted to authorized members of the Oxara Development team.
# Any other use requires prior written approval from Oxara Development.

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from db.database import init_database
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import text

console = Console()


async def _nuke(database_url: str, skip_confirm: bool) -> None:
    # Initialise database
    try:
        db = init_database(database_url)
    except ValueError as e:
        console.print(f'[bold red]✗ {e}[/bold red]')
        sys.exit(1)

    # Health check
    with console.status('[cyan]Checking database connection...[/cyan]'):
        healthy = await db.health_check()

    if not healthy:
        console.print('[bold red]✗ Could not reach the database. Aborting.[/bold red]')
        await db.dispose()
        sys.exit(1)

    console.print('[bold green]✓ Database connection OK[/bold green]')

    # Fetch table list
    try:
        async with db.engine.connect() as conn:
            result = await conn.execute(
                text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            )
            tables = [row[0] for row in result.fetchall()]
    except Exception as e:
        console.print(f'[bold red]✗ Failed to fetch tables: {e}[/bold red]')
        await db.dispose()
        sys.exit(1)

    # Show what's about to be destroyed
    tbl = Table(box=box.ROUNDED, border_style='red', show_header=True)
    tbl.add_column('Tables to be destroyed', style='bold white')
    for t in tables:
        tbl.add_row(t)

    console.print()
    console.print(tbl)
    console.print()
    console.print(
        Panel(
            f'[bold red]This will permanently destroy {len(tables)} table(s).\n'
            'This action is IRREVERSIBLE. All data will be lost.[/bold red]',
            border_style='red',
            expand=False,
        )
    )
    console.print()

    if not skip_confirm:
        try:
            confirm = input('  Type "nuke" to confirm: ').strip()
        except KeyboardInterrupt, EOFError:
            console.print('\n[yellow]Aborted.[/yellow]')
            await db.dispose()
            sys.exit(0)

        if confirm != 'nuke':
            console.print('[yellow]Aborted.[/yellow]')
            await db.dispose()
            sys.exit(0)
        console.print()

    # Drop and recreate
    try:
        with console.status('[cyan]Dropping schema...[/cyan]'):
            async with db.engine.begin() as conn:
                await conn.execute(text('DROP SCHEMA public CASCADE'))
                await conn.execute(text('CREATE SCHEMA public'))
    except Exception as e:
        console.print(f'[bold red]✗ Failed to drop/recreate schema: {e}[/bold red]')
        await db.dispose()
        sys.exit(1)

    console.print('[bold green]✓ Schema dropped and recreated[/bold green]')

    # Final health check
    with console.status('[cyan]Verifying...[/cyan]'):
        healthy = await db.health_check()

    if not healthy:
        console.print('[bold red]✗ Post-nuke health check failed.[/bold red]')
        await db.dispose()
        sys.exit(1)

    await db.dispose()

    console.print('[bold green]✓ Verification passed[/bold green]')
    console.print()
    console.print(
        Panel('[bold green]Database nuked and recreated successfully.[/bold green]', border_style='green', expand=False)
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Drop and recreate the public schema.')
    parser.add_argument(
        '--url',
        '-url',
        nargs='?',
        default=os.getenv('DATABASE_URL'),
        help='Database URL (e.g. postgresql+asyncpg://user:pass@host/db). Falls back to $DATABASE_URL.',
    )
    parser.add_argument('--yes', '-y', action='store_true', help='Skip confirmation prompt.')
    args = parser.parse_args()

    if not args.url:
        console.print('[bold red]✗ No database URL provided.[/bold red]')
        console.print('[dim]Pass it as an argument or set the DATABASE_URL environment variable.[/dim]')
        sys.exit(1)

    if args.url.startswith('postgresql://'):
        args.url = args.url.replace('postgresql://', 'postgresql+asyncpg://', 1)

    asyncio.run(_nuke(database_url=args.url, skip_confirm=args.yes))
