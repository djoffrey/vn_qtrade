# -*- coding: utf-8 -*-

"""
This file defines the Text-based User Interface (TUI) for the vn_qtrade application.
It uses the 'textual' library to create a rich, interactive terminal interface for trading.
"""

from datetime import datetime, timezone
from typing import List

# Textual imports for building the TUI
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, DataTable, Log
from textual.containers import Horizontal, Vertical

# --- Custom Widgets for Each Panel ---

class PositionsPanel(Static):
    """
    A widget to display the user's current positions in a table.
    """

    def compose(self) -> ComposeResult:
        """
        Compose the content of the PositionsPanel.
        This will create a DataTable to show position information.
        """
        yield DataTable()

    def on_mount(self) -> None:
        """
        Called when the widget is mounted.
        Initializes the table with headers and dummy data.
        """
        table = self.query_one(DataTable)
        table.add_columns("Symbol", "Direction", "Volume", "Avg Price", "PnL")
        
        # Add dummy data
        dummy_positions = [
            ("BTC-USDT-SWAP", "[bold green]LONG[/]", "0.5", "68000.50", "[green]+150.25[/]"),
            ("ETH-USDT-SWAP", "[bold red]SHORT[/]", "10.0", "3500.00", "[red]-80.55[/]"),
        ]
        for pos in dummy_positions:
            table.add_row(*pos)

    def update_positions(self, positions: List[dict]) -> None:
        """
        Updates the positions table with new data from the trading engine.

        Args:
            positions (List[dict]): A list of dictionaries, where each dictionary
                                    represents a position's data.
        """
        table = self.query_one(DataTable)
        table.clear()
        # This method will clear the existing rows and add the new position data.
        pass


class OrderBookPanel(Static):
    """
    A widget to display the order book (market depth) for a selected symbol.
    """

    def compose(self) -> ComposeResult:
        """
        Compose the content of the OrderBookPanel.
        This will create two tables: one for bids and one for asks.
        """
        yield Horizontal(
            DataTable(id="bids", show_header=True),
            DataTable(id="asks", show_header=True)
        )

    def on_mount(self) -> None:
        """
        Called when the widget is mounted.
        Initializes the bid and ask tables with headers and dummy data.
        """
        bids_table = self.query_one("#bids", DataTable)
        asks_table = self.query_one("#asks", DataTable)
        
        bids_table.add_columns("Price (BID)", "Volume")
        asks_table.add_columns("Price (ASK)", "Volume")

        # Add dummy data
        dummy_bids = [
            ("[green]68500.00[/]", "0.5"), ("[green]68499.50[/]", "1.2"), 
            ("[green]68499.00[/]", "2.0"), ("[green]68498.50[/]", "3.5"),
        ]
        dummy_asks = [
            ("[red]68500.50[/]", "0.8"), ("[red]68501.00[/]", "1.5"),
            ("[red]68501.50[/]", "2.2"), ("[red]68502.00[/]", "4.0"),
        ]

        for bid in dummy_bids:
            bids_table.add_row(*bid)
        for ask in dummy_asks:
            asks_table.add_row(*ask)


    def update_order_book(self, tick_data: dict) -> None:
        """
        Updates the order book display with new tick data.

        Args:
            tick_data (dict): A dictionary containing the latest tick data,
                              including bids and asks.
        """
        # This method will update the bid and ask tables.
        pass


class TradesPanel(Static):
    """
    A widget to display the latest market trades for a selected symbol.
    """

    def compose(self) -> ComposeResult:
        """
        Compose the content of the TradesPanel.
        This will create a DataTable to show recent trades.
        """
        yield DataTable()

    def on_mount(self) -> None:
        """
        Called when the widget is mounted.
        Initializes the trades table with headers and dummy data.
        """
        table = self.query_one(DataTable)
        table.add_columns("Time", "Price", "Volume", "Direction")

        # Add dummy data
        now = datetime.now(timezone.utc)
        dummy_trades = [
            (now.strftime("%H:%M:%S"), "[red]68501.00[/]", "0.2", "[red]SELL[/]"),
            (now.strftime("%H:%M:%S"), "[green]68500.50[/]", "0.1", "[green]BUY[/]"),
            (now.strftime("%H:%M:%S"), "[red]68501.50[/]", "0.5", "[red]SELL[/]"),
        ]
        for trade in dummy_trades:
            table.add_row(*trade)

    def add_trade(self, trade_data: dict) -> None:
        """
        Adds a new trade to the top of the trades display.

        Args:
            trade_data (dict): A dictionary containing the new trade's data.
        """
        # This method will add a new row to the DataTable.
        pass


class LogPanel(Static):
    """
    A widget to display log messages from the trading engine and the TUI itself.
    """

    def compose(self) -> ComposeResult:
        """
        Compose the content of the LogPanel.
        This uses textual's built-in Log widget.
        """
        yield Log()

    def add_log_message(self, message: str) -> None:
        """
        Writes a new message to the log.

        Args:
            message (str): The log message to display.
        """
        log_widget = self.query_one(Log)
        log_widget.write_line(message)


# --- Main Trading Application ---

class TradeApp(App):
    """
    The main application class for the vn_qtrade TUI.
    """

    CSS_PATH = "tui.css"

    BINDINGS = [
        ("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        """
        Compose the main layout of the application.
        """
        yield Header()
        yield Horizontal(
            Vertical(
                PositionsPanel(id="positions"),
                LogPanel(id="log_ai"),
                classes="column",
            ),
            Vertical(
                OrderBookPanel(id="order_book"),
                TradesPanel(id="trades"),
                classes="column",
            ),
        )
        yield Footer()

    def on_mount(self) -> None:
        """
        Called when the application is mounted.
        """
        # Add initial log messages
        log_panel = self.query_one(LogPanel)
        log_panel.add_log_message("TUI Application Started.")
        log_panel.add_log_message("Waiting for engine connection...")
        
        # For now, we are not starting the real engine.
        # self.start_engine_thread()

    def start_engine_thread(self) -> None:
        """
        Initializes and starts the OKXEngine in a background thread.
        """
        pass

    # --- Event Handlers from Engine ---

    def on_position_update(self, event_data: dict) -> None:
        """
        Handles position update events from the engine.
        """
        positions_panel = self.query_one(PositionsPanel)
        positions_panel.update_positions(event_data['positions'])

    def on_tick_update(self, event_data: dict) -> None:
        """
        Handles tick update events from the engine.
        """
        order_book_panel = self.query_one(OrderBookPanel)
        order_book_panel.update_order_book(event_data['tick'])

    def on_trade_update(self, event_data: dict) -> None:
        """
        Handles new trade events from the engine.
        """
        trades_panel = self.query_one(TradesPanel)
        trades_panel.add_trade(event_data['trade'])

    def on_log_message(self, event_data: dict) -> None:
        """
        Handles log messages from the engine.
        """
        log_panel = self.query_one(LogPanel)
        log_panel.add_log_message(event_data['message'])


if __name__ == "__main__":
    app = TradeApp()
    app.run()