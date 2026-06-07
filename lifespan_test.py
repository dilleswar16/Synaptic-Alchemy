import asyncio, os
os.environ.setdefault("DB_BACKEND", "sqlite")
os.environ.setdefault("CORVIN_ENV", "local")

from corvin.storage.db import get_engine, is_sqlite
from corvin.storage.models import Base
from corvin.core.config_loader import get_env, load_config
from corvin.slo.snapshot import run_forever as slo_run_forever

async def test_lifespan():
    print("Step 1: is_sqlite check", flush=True)
    if is_sqlite():
        print("Step 2: create_all", flush=True)
        Base.metadata.create_all(get_engine())
        print("Step 2: done", flush=True)
    print("Step 3: load policy", flush=True)
    policy = load_config("policies/investigation", get_env())
    pred_bg = policy.get("predictive_background_enabled")
    print(f"Step 3: done, predictive_bg={pred_bg}", flush=True)
    print("Step 4: creating slo task", flush=True)
    slo_interval = int(policy.get("slo_snapshot_interval_seconds", 3600))
    slo_task = asyncio.create_task(slo_run_forever(interval_seconds=slo_interval))
    print("Step 4: slo task created", flush=True)
    print("Step 5: YIELD would happen here - startup complete!", flush=True)
    await asyncio.sleep(0.1)  # let the task run one tick
    slo_task.cancel()
    print("LIFESPAN TEST PASSED", flush=True)

asyncio.run(test_lifespan())
