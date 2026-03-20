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


@app.post("/user/deposit", response_model=TxResponse)
def user_deposit(body: DepositModel):
    account = _build_account(body.from_key)
    tx = contract.functions.deposit(body.pool_id, body.amount_wei).build_transaction(
        {"from": account.address}
    )
    res = _send_tx(account, tx)
    _record_activity("deposit", account.address, body.pool_id, body.amount_wei, res.tx_hash, res.block_number, res.status)
    return res


@app.post("/user/withdraw", response_model=TxResponse)
def user_withdraw(body: WithdrawModel):
    account = _build_account(body.from_key)
    tx = contract.functions.withdraw(body.pool_id, body.amount_wei).build_transaction(
        {"from": account.address}
    )
    res = _send_tx(account, tx)
    _record_activity("withdraw", account.address, body.pool_id, body.amount_wei, res.tx_hash, res.block_number, res.status)
    return res


@app.post("/user/exit-all", response_model=TxResponse)
def user_exit_all(body: ExitAllModel):
    account = _build_account(body.from_key)
    tx = contract.functions.exitAll(body.pool_id).build_transaction(
        {"from": account.address}
    )
    res = _send_tx(account, tx)
    _record_activity("exit_all", account.address, body.pool_id, 0, res.tx_hash, res.block_number, res.status)
    return res


@app.post("/user/claim-fortune", response_model=TxResponse)
def user_claim_fortune(body: ClaimFortuneModel):
    account = _build_account(body.from_key)
    tx = contract.functions.claimFortuneYield(
        body.pool_id,
        Web3.to_checksum_address(body.to),
    ).build_transaction({"from": account.address})
    res = _send_tx(account, tx)
    _record_activity("claim", account.address, body.pool_id, 0, res.tx_hash, res.block_number, res.status)
    return res


@app.get("/fortune/preview", response_model=FortunePreview)
def fortune_preview(user: str, pool_id: int):
    addr = Web3.to_checksum_address(user)
    pending = contract.functions.previewPendingFortune(addr, pool_id).call()
    projected = contract.functions.projectedFortuneScore(addr, pool_id).call()
    claimable = contract.functions.previewClaimableReward(addr, pool_id).call()
    return FortunePreview(
        user=addr,
        pool_id=pool_id,
        pending_fortune=pending,
        projected_fortune=projected,
        claimable_reward=claimable,
    )


@app.get("/fortune/cycle", response_model=CycleView)
def fortune_cycle():
    raw = contract.functions.currentLuckCycle().call()
    cid, lucky_block, fortune_delta = raw
    return CycleView(id=cid, lucky_block=lucky_block, fortune_delta=fortune_delta)


@app.get("/fortune/oracle-hint", response_model=OracleHintView)
def fortune_oracle_hint(user: str, pool_id: int, oracle_seed: int = 0):
    addr = Web3.to_checksum_address(user)
    seed = oracle_seed or int(time.time())
    hinted = contract.functions.oracleHintedLuck(addr, pool_id, seed).call()
    return OracleHintView(
        user=addr,
        pool_id=pool_id,
        oracle_seed=seed,
        hinted_luck=hinted,
    )


@app.get("/analytics/summary")
def analytics_summary():
    stats = _aggregate_stats()
    return {
        "total_deposited": stats.total_deposited,
        "total_withdrawn": stats.total_withdrawn,
        "net_flow": stats.net_flow,
        "unique_users": stats.unique_users,
        "pools_seen": stats.pools_seen,
        "recent_events": [asdict(ev) for ev in stats.recent_events],
    }


def _filter_events(
    user: t.Optional[str],
    pool_id: t.Optional[int],
    event_type: t.Optional[str],
) -> t.List[ActivityEvent]:
    user_norm = Web3.to_checksum_address(user) if user else None
    et_norm = event_type.lower().strip() if event_type else None
    out: t.List[ActivityEvent] = []
    for ev in _activity_events:
        if user_norm and ev.user != user_norm:
            continue
        if pool_id is not None and ev.pool_id != pool_id:
            continue
        if et_norm and ev.event_type != et_norm:
            continue
        out.append(ev)
    return out


@app.get("/analytics/events")
def analytics_events(
    user: t.Optional[str] = None,
    pool_id: t.Optional[int] = None,
    event_type: t.Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    """
    Returns recent events captured by this Ate8 instance, optionally filtered
    by user, pool, and event type. Uses offset/limit for pagination.
    """
    if limit < 1:
        limit = 1
    if limit > 500:
        limit = 500
    if offset < 0:
        offset = 0

    items = _filter_events(user, pool_id, event_type)
    page = items[offset : offset + limit]
    return {
        "total": len(items),
        "offset": offset,
        "limit": limit,
        "events": [asdict(ev) for ev in page],
    }


@app.get("/analytics/events.csv", response_class=PlainTextResponse)
def analytics_events_csv(
    user: t.Optional[str] = None,
    pool_id: t.Optional[int] = None,
    event_type: t.Optional[str] = None,
    limit: int = 500,
    offset: int = 0,
):
    """
    CSV export of the filtered event timeline.
    """
    if limit < 1:
        limit = 1
    if limit > 5_000:
        limit = 5_000
    if offset < 0:
        offset = 0

    items = _filter_events(user, pool_id, event_type)
    page = items[offset : offset + limit]
    header = "ts,event_type,user,pool_id,amount,tx_hash,block_number,status"
    lines = [header]
    for ev in page:
        bn = "" if ev.block_number is None else str(ev.block_number)
        st = "" if ev.status is None else str(ev.status)
        lines.append(
            f"{ev.ts},{ev.event_type},{ev.user},{ev.pool_id},{ev.amount},{ev.tx_hash},{bn},{st}"
        )
    return "\n".join(lines) + "\n"


@app.get("/pools/snapshot")
def pools_snapshot(ids: str):
    """
    Accepts a comma-separated list of pool IDs and returns a snapshot
    of configuration and aggregate metadata for each.
    """
    try:
        pool_ids = [int(x) for x in ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid pool id list")
    snap = contract.functions.snapshotPools(pool_ids).call()
    out = []
    for item in snap:
        out.append(
            {
                "poolId": item[0],
                "asset": item[1],
                "leverageFactorBps": item[2],
                "active": item[3],
                "seasoningFactor": item[4],
                "streakBonusBps": item[5],
                "poolCap": item[6],
                "minDeposit": item[7],
                "allowlistedOnly": item[8],
                "totalPrincipal": item[9],
            }
        )
    return out


@app.post("/portfolio/view")
def portfolio_view(body: PortfolioQuery):
    """
    Returns an aggregated view of a user's positions across selected pools.
    """
    addr = Web3.to_checksum_address(body.user)
    views = contract.functions.userPortfolioView(addr, body.pool_ids).call()
    result = []
    for v in views:
        result.append(
            {
                "poolId": v[0],
                "principal": v[1],
                "fortunePoints": v[2],
                "fortuneClaimed": v[3],
                "enteredAtBlock": v[4],
                "lastFortuneBlock": v[5],
                "pendingFortune": v[6],
                "claimableReward": v[7],
            }
        )
    return result


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("Ate8:app", host="0.0.0.0", port=int(os.getenv("ATE8_PORT", "8088")), reload=False)

"""
    Ate8 Operational Appendix
    -------------------------
    The additional documentation below is purely descriptive and
    expands on the purpose, behavior, and recommended usage patterns
    of the Ate8 control plane. It is intentionally verbose to act
    as inline operations runbook material.

    1. Role of Ate8
       Ate8 sits as a stateless-or-lightly-stateful translation layer
       between HTTP clients (browsers, automation scripts, monitoring
       tools) and the EightyEightFinacio smart contract. Instead of
       forcing every caller to know ABI details, gas settings, and
       signing flows, Ate8 offers a narrow set of JSON endpoints that
       wrap these concerns in a controlled environment.

       The design philosophy is:
       - be explicit about which actor is taking which action
         (guardian, treasurer, end-user),
       - centralise RPC configuration and contract address knowledge,
       - provide simple summaries of protocol health and activity.

    2. Environment Configuration Notes
       A minimal .env-style setup for a local test environment might
       include:

           ATE8_RPC=http://localhost:8545
           ATE8_CHAIN_ID=1337
           ATE8_CONTRACT=0x0000000000000000000000000000000000000000
           ATE8_GUARDIAN_KEY=0x<guardian-private-key-hex>
           ATE8_TREASURER_KEY=0x<treasurer-private-key-hex>

       In higher-value environments, these secrets should live in a
       secure secret manager or hardware-backed signer, and Ate8 may
       evolve to delegate signing to those services instead of holding
       private keys directly.

    3. Endpoint Overview
       - /health
         Quick connectivity and deployment status: confirms RPC reach
         ability and returns the latest block plus configured contract
         address.

       - /guardian/configure-pool
         Adds or updates a pool. Called rarely, usually after deploying
         a new asset or adjusting risk parameters. This endpoint also
         opportunistically updates seasoning and streak bonuses if
         provided.

       - /treasurer/reward-stream
         Wires in a reward token and a scaled rate value to map
         fortune into tangible yield.

       - /guardian/advance-cycle
         Steps the luck cycle forward. This is mostly ceremonial from
         an external point of view but can drive UI flows that respond
         to cycle IDs and lucky block predictions.

       - /user/deposit, /user/withdraw, /user/exit-all
         Core liquidity operations. These are the primary actions an
         end-user takes when interacting with the protocol through
         a trusted Ate8 instance.

       - /user/claim-fortune
         Claims any reward mapped from fortune into the reward token.

       - /fortune/preview, /fortune/cycle, /fortune/oracle-hint
         Read-only insight endpoints, heavily used by Magico88 and
         any monitoring dashboards.

       - /analytics/summary
         Offers a snapshot of recent flows as seen through this Ate8
         process. It is not a canonical ledger but a useful auxiliary
         lens for operators.

    4. Activity Accounting Notes
       The in-memory analytics are intentionally simple and bounded:
       - _activity_events is a deque with a fixed maximum length so
         that it cannot grow unbounded in RAM.
       - Totals are tracked per pool and summarised across all pools.
       - A set of user addresses observed through this process is
         kept for uniqueness counts.

       This design trades completeness for observability with minimal
       complexity. For production-grade history, on-chain logs and an
       indexing subsystem should be preferred.

    5. Error Handling Rationale
       - Invalid private keys result in HTTP 400 errors with a short
         explanation taken from the underlying library.
       - RPC send or receipt wait failures still return the tx_hash
         so that external tooling can continue tracking the
         transaction even if Ate8 briefly lost visibility.

    6. Extension Ideas
       Possible further extensions for Ate8 include:
       - WebSocket streaming of activity events for real-time UI
         updates without polling.
       - Pluggable authentication / rate limiting middleware that
         restricts high-privilege endpoints to specific operators.
       - Integration with structured logging systems and metrics
         exporters for infrastructure monitoring.

    7. Security Considerations
       Care must be taken when deploying Ate8 in contexts where private
       keys are held in-process:
       - expose only on hardened networks,
       - use TLS termination at a trusted boundary,
       - consider IP whitelisting or mutual TLS for guardian and
         treasurer-level endpoints,
       - monitor for anomalous request patterns.

    8. Developer Onboarding Story
       A new engineer joining an EightyEightFinacio deployment can:
       - read this appendix plus the main FastAPI router definitions,
       - run Ate8 locally against a devnet,
       - inspect the JSON interactions in Magico88’s browser console,
       - progressively extend this service with additional inspection
         tools as needed without changing the underlying contract.
"""
