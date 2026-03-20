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
    w3_local = Web3(Web3.HTTPProvider(cfg.rpc_url))
    if not w3_local.is_connected():
        raise RuntimeError(f"Ate8 could not connect to RPC at {cfg.rpc_url}")
    w3_local.middleware_onion.inject(geth_poa_middleware, layer=0)
    return w3_local


EIGHTY_EIGHT_ABI: t.List[dict] = [
    {
        "inputs": [
            {"internalType": "uint256", "name": "poolId", "type": "uint256"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "deposit",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "poolId", "type": "uint256"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "withdraw",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "poolId", "type": "uint256"},
        ],
        "name": "exitAll",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "poolId", "type": "uint256"},
            {"internalType": "address", "name": "to", "type": "address"},
        ],
        "name": "claimFortuneYield",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "user", "type": "address"},
            {"internalType": "uint256", "name": "poolId", "type": "uint256"},
        ],
        "name": "previewPendingFortune",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "user", "type": "address"},
            {"internalType": "uint256", "name": "poolId", "type": "uint256"},
        ],
        "name": "projectedFortuneScore",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "user", "type": "address"},
            {"internalType": "uint256", "name": "poolId", "type": "uint256"},
        ],
        "name": "previewClaimableReward",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "currentLuckCycle",
        "outputs": [
            {
                "components": [
                    {"internalType": "uint64", "name": "id", "type": "uint64"},
                    {"internalType": "uint64", "name": "luckyBlock", "type": "uint64"},
                    {"internalType": "uint128", "name": "fortuneDelta", "type": "uint128"},
                ],
                "internalType": "struct EightyEightFinacio.CycleInfo",
                "name": "",
                "type": "tuple",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "seedHint", "type": "uint256"},
        ],
        "name": "advanceLuckCycle",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "poolId", "type": "uint256"},
            {"internalType": "address", "name": "asset", "type": "address"},
            {"internalType": "uint96", "name": "leverageFactorBps", "type": "uint96"},
            {"internalType": "bool", "name": "active", "type": "bool"},
        ],
        "name": "configurePool",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "poolId", "type": "uint256"},
            {"internalType": "uint64", "name": "seasoningFactor", "type": "uint64"},
            {"internalType": "uint64", "name": "streakBonusBps", "type": "uint64"},
        ],
        "name": "updatePoolSeasoning",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "token", "type": "address"},
            {"internalType": "uint128", "name": "ratePerBlockScaled", "type": "uint128"},
            {"internalType": "bool", "name": "active", "type": "bool"},
        ],
        "name": "setRewardStream",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "user", "type": "address"},
            {"internalType": "uint256", "name": "poolId", "type": "uint256"},
            {"internalType": "uint256", "name": "oracleSeed", "type": "uint256"},
        ],
        "name": "oracleHintedLuck",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "uint256[]", "name": "poolIds", "type": "uint256[]"},
        ],
        "name": "snapshotPools",
        "outputs": [
            {
                "components": [
                    {"internalType": "uint256", "name": "poolId", "type": "uint256"},
                    {"internalType": "address", "name": "asset", "type": "address"},
                    {"internalType": "uint96", "name": "leverageFactorBps", "type": "uint96"},
                    {"internalType": "bool", "name": "active", "type": "bool"},
                    {"internalType": "uint64", "name": "seasoningFactor", "type": "uint64"},
                    {"internalType": "uint64", "name": "streakBonusBps", "type": "uint64"},
                    {"internalType": "uint256", "name": "poolCap", "type": "uint256"},
                    {"internalType": "uint256", "name": "minDeposit", "type": "uint256"},
                    {"internalType": "bool", "name": "allowlistedOnly", "type": "bool"},
                    {"internalType": "uint256", "name": "totalPrincipal", "type": "uint256"},
                ],
                "internalType": "struct EightyEightFinacio.PoolSnapshot[]",
                "name": "",
                "type": "tuple[]",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "user", "type": "address"},
            {"internalType": "uint256[]", "name": "poolIds", "type": "uint256[]"},
        ],
        "name": "userPortfolioView",
        "outputs": [
            {
                "components": [
                    {"internalType": "uint256", "name": "poolId", "type": "uint256"},
                    {"internalType": "uint192", "name": "principal", "type": "uint192"},
                    {"internalType": "uint192", "name": "fortunePoints", "type": "uint192"},
                    {"internalType": "uint192", "name": "fortuneClaimed", "type": "uint192"},
                    {"internalType": "uint64", "name": "enteredAtBlock", "type": "uint64"},
                    {"internalType": "uint64", "name": "lastFortuneBlock", "type": "uint64"},
                    {"internalType": "uint256", "name": "pendingFortune", "type": "uint256"},
                    {"internalType": "uint256", "name": "claimableReward", "type": "uint256"},
                ],
                "internalType": "struct EightyEightFinacio.UserPoolView[]",
                "name": "",
                "type": "tuple[]",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    },
]


cfg = load_network_config()
w3 = build_web3(cfg)
contract = w3.eth.contract(address=Web3.to_checksum_address(cfg.contract_address), abi=EIGHTY_EIGHT_ABI)

app = FastAPI(title="Ate8 – 88Finacio Control Plane")

app.add_middleware(
    CORSMiddleware,
