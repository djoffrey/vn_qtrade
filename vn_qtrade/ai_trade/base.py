"""
Base objects for AI Agent.
"""

from dataclasses import dataclass
from datetime import datetime

from vnpy_evo.trader.constant import Direction, Offset
from vnpy_evo.trader.event import EVENT_LOG

# Define the new event type for AI signals
EVENT_AI_SIGNAL = "eAiSignal"


@dataclass
class SignalData:
    """
    The data structure for carrying AI-generated trading signals.
    This object will be passed as the data of the EVENT_AI_SIGNAL event.
    """
    vt_symbol: str
    direction: Direction
    price: float
    volume: float

    signal_id: str = ""
    agent_id: str = ""
    datetime: datetime = None
    confidence: float = 0.0
    rationale: str = ""

    def __post_init__(self):
        """
        Generate signal_id and datetime if they are not provided.
        """
        if not self.datetime:
            self.datetime = datetime.now()

        if not self.signal_id:
            self.signal_id = f"{self.datetime.strftime('%Y%m%d%H%M%S')}_{self.vt_symbol}"

