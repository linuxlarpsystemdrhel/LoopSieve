"""Mount the optional Textual workbench headlessly with isolated state."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch

from textual.app import App
from textual.widgets import DataTable, TabbedContent

from loopsieve.tui import launch


async def check(app: App):
    async with app.run_test() as pilot:
        await pilot.pause()
        tabs = app.query_one("#tabs", TabbedContent)
        assert tabs.active == "dashboard", tabs.active
        assert app.query_one("#table-provider-health", DataTable).row_count > 0
        table = app.query_one("#table-capabilities", DataTable)
        assert table.row_count > 0 and len(table.columns) == 4


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        with (
            patch.dict(
                "os.environ",
                {"LOOPSIEVE_STATE_DIR": str(root / "state"), "CLAUDE_PLUGIN_DATA": ""},
            ),
            patch.object(App, "run", lambda app: asyncio.run(check(app))),
        ):
            assert launch(root) == 0
    print("Textual mounted with Dashboard, Provider Health and Capabilities")


if __name__ == "__main__":
    main()
