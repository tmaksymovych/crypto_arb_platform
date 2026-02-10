from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional


class Ticker(BaseModel):
    symbol: str
    exchange: str

    bid: float #price we can sell
    ask: float #price we can buy
    volume: float #number of shares traded USD

    can_withdraw: bool = True
    can_deposit: bool = True

    timestamp: float = Field(default_factory=lambda: datetime.now().timestamp())


    @field_validator('bid', 'ask', 'volume')
    @classmethod
    def check_positive(cls, v:float) -> float:
        if v < 0:
            raise ValueError('Value must be non-negative')
        return v

    @property
    def internal_spread(self) -> float:
        """
        Calculate the internal spread between ask and bid prices.
        """
        if self.bid == 0:
            return 0.0
        return ((self.ask - self.bid) / self.bid) * 100
    


class NetworkStatus(BaseModel):
    name: str
    deposit: bool
    withdraw: bool
    fee : Optional[float] #fee for withdrawal, if applicable

class CurrencyStatus(BaseModel):
    symbol: str
    exchange: str
    networks: dict[str, NetworkStatus] # list of networks for this currency, e.g. {'ERC20': NetworkStatus(...), 'BEP20': NetworkStatus(...)}

    