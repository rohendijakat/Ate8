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
