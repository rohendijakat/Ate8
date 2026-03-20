import os
import time
import typing as t
from dataclasses import dataclass, asdict
from collections import defaultdict, deque

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from web3 import Web3
from web3.middleware import geth_poa_middleware


class NetworkConfig(BaseModel):
    rpc_url: str
    chain_id: int
    contract_address: str
    guardian_key: str
    treasurer_key: str


class PoolConfigModel(BaseModel):
    pool_id: int = Field(0, description="0 to create new pool")
    asset: str
    leverage_factor_bps: int = Field(ge=100, le=88888)
    active: bool = True
    seasoning_factor: int = Field(default=0, ge=0)
    streak_bonus_bps: int = Field(default=0, ge=0, le=8888)


class DepositModel(BaseModel):
    pool_id: int
    amount_wei: int
    from_key: str


class WithdrawModel(BaseModel):
    pool_id: int
    amount_wei: int
    from_key: str


class ExitAllModel(BaseModel):
    pool_id: int
    from_key: str


class AdvanceCycleModel(BaseModel):
    seed_hint: int = Field(default_factory=lambda: int(time.time()))


class RewardConfigModel(BaseModel):
    token: str
    rate_per_block_scaled: int = Field(ge=0)
    active: bool = True


class ClaimFortuneModel(BaseModel):
    pool_id: int
    to: str
    from_key: str


class PortfolioQuery(BaseModel):
    user: str
    pool_ids: t.List[int]


class TxResponse(BaseModel):
    tx_hash: str
    block_number: t.Optional[int] = None
    status: t.Optional[int] = None


@dataclass
class PoolView:
    pool_id: int
    asset: str
    leverage_factor_bps: int
    active: bool
    seasoning_factor: int
    streak_bonus_bps: int


@dataclass
class FortunePreview:
    user: str
    pool_id: int
    pending_fortune: int
    projected_fortune: int
    claimable_reward: int


@dataclass
class CycleView:
    id: int
    lucky_block: int
    fortune_delta: int


@dataclass
class OracleHintView:
    user: str
    pool_id: int
    oracle_seed: int
    hinted_luck: int


@dataclass
class ActivityEvent:
    ts: float
    event_type: str
    user: str
    pool_id: int
    amount: int
    tx_hash: str
    block_number: t.Optional[int] = None
    status: t.Optional[int] = None


@dataclass
class AggregateStats:
    total_deposited: int
    total_withdrawn: int
    net_flow: int
    unique_users: int
    pools_seen: int
    recent_events: t.List[ActivityEvent]


def load_network_config() -> NetworkConfig:
    return NetworkConfig(
        rpc_url=os.getenv("ATE8_RPC", "http://localhost:8545"),
        chain_id=int(os.getenv("ATE8_CHAIN_ID", "1337")),
        contract_address=os.getenv("ATE8_CONTRACT", "0x0000000000000000000000000000000000000000"),
        guardian_key=os.getenv("ATE8_GUARDIAN_KEY", "0x" + "1" * 64),
        treasurer_key=os.getenv("ATE8_TREASURER_KEY", "0x" + "2" * 64),
    )


def build_web3(cfg: NetworkConfig) -> Web3:
