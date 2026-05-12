# Copyright (C) 2026 dev-737
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://gnu.org>.

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

load_dotenv()

production: bool = os.getenv('PRODUCTION', 'False').lower() in ('true', '1', 't')
is_debug_mode: bool = os.getenv('DEBUG', 'False').lower() in ('true', '1', 't')

if not production:
    from rich.console import Console
    from rich.logging import RichHandler
    from rich.theme import Theme

    console = Console(
        theme=Theme({
            'logging.level.info': '#a6e3a1',
            'logging.level.debug': '#8aadf4',
            'logging.level.warning': '#f9e2af',
            'logging.level.error': '#f38ba8',
        })
    )
    handler: logging.Handler = RichHandler(tracebacks_width=200, console=console)
else:
    handler = logging.StreamHandler()

handler.setFormatter(logging.Formatter('%(name)s: %(message)s'))

logger: logging.Logger = logging.getLogger('db')
logger.setLevel(logging.DEBUG if is_debug_mode else logging.INFO)
logger.addHandler(handler)
logger.propagate = False
