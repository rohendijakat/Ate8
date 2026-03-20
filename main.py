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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


_activity_events: deque[ActivityEvent] = deque(maxlen=512)
_totals_deposited: defaultdict[int, int] = defaultdict(int)
_totals_withdrawn: defaultdict[int, int] = defaultdict(int)
_users_seen: set[str] = set()


def _record_activity(
    event_type: str,
    user: str,
    pool_id: int,
    amount: int,
    tx_hash: str,
    block_number: t.Optional[int] = None,
    status: t.Optional[int] = None,
) -> None:
    ev = ActivityEvent(
        ts=time.time(),
        event_type=event_type,
        user=user,
        pool_id=pool_id,
        amount=amount,
        tx_hash=tx_hash,
        block_number=block_number,
        status=status,
    )
    _activity_events.appendleft(ev)
    _users_seen.add(user)
    if event_type == "deposit":
        _totals_deposited[pool_id] += amount
    elif event_type in ("withdraw", "exit_all"):
        _totals_withdrawn[pool_id] += amount


def _aggregate_stats() -> AggregateStats:
    total_deposited = sum(_totals_deposited.values())
    total_withdrawn = sum(_totals_withdrawn.values())
    net = total_deposited - total_withdrawn
    pools_seen = len(set(list(_totals_deposited.keys()) + list(_totals_withdrawn.keys())))
    return AggregateStats(
        total_deposited=total_deposited,
        total_withdrawn=total_withdrawn,
        net_flow=net,
        unique_users=len(_users_seen),
        pools_seen=pools_seen,
        recent_events=list(_activity_events),
    )


def _build_account(pk: str):
    try:
        return w3.eth.account.from_key(pk)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid private key: {exc}")


def _send_tx(account, tx) -> TxResponse:
    tx["nonce"] = w3.eth.get_transaction_count(account.address)
    if "gasPrice" not in tx:
        tx["gasPrice"] = w3.eth.gas_price
    if "chainId" not in tx:
        tx["chainId"] = cfg.chain_id

    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
    try:
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
        return TxResponse(
            tx_hash=tx_hash.hex(),
            block_number=receipt.blockNumber,
            status=receipt.status,
        )
    except Exception:
        return TxResponse(tx_hash=tx_hash.hex())


@app.get("/health")
def health():
    latest = w3.eth.block_number
    return {"status": "ok", "block": latest, "contract": cfg.contract_address}


@app.get("/debug/config")
def debug_config():
    return {
        "rpc_url": cfg.rpc_url,
        "chain_id": cfg.chain_id,
        "contract_address": cfg.contract_address,
        "guardian_address": w3.eth.account.from_key(cfg.guardian_key).address,
        "treasurer_address": w3.eth.account.from_key(cfg.treasurer_key).address,
    }


@app.post("/guardian/configure-pool", response_model=TxResponse)
def configure_pool(body: PoolConfigModel):
    guardian = _build_account(cfg.guardian_key)
    tx = contract.functions.configurePool(
        body.pool_id,
        Web3.to_checksum_address(body.asset),
        body.leverage_factor_bps,
        body.active,
    ).build_transaction(
        {"from": guardian.address}
    )
    res = _send_tx(guardian, tx)
    if res.status is None or res.status == 1:
        if body.seasoning_factor or body.streak_bonus_bps:
            tx2 = contract.functions.updatePoolSeasoning(
                body.pool_id or 1,
                body.seasoning_factor,
                body.streak_bonus_bps,
            ).build_transaction({"from": guardian.address})
            _send_tx(guardian, tx2)
    return res


@app.post("/treasurer/reward-stream", response_model=TxResponse)
def treasurer_reward_stream(body: RewardConfigModel):
    treasurer = _build_account(cfg.treasurer_key)
    tx = contract.functions.setRewardStream(
        Web3.to_checksum_address(body.token),
        body.rate_per_block_scaled,
        body.active,
    ).build_transaction({"from": treasurer.address})
    return _send_tx(treasurer, tx)


@app.post("/guardian/advance-cycle", response_model=TxResponse)
def guardian_advance_cycle(body: AdvanceCycleModel):
    guardian = _build_account(cfg.guardian_key)
    tx = contract.functions.advanceLuckCycle(body.seed_hint).build_transaction(
        {"from": guardian.address}
    )
    return _send_tx(guardian, tx)


