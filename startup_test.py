import sys, os, traceback
os.environ['DB_BACKEND'] = 'sqlite'

def step(n, msg):
    print(f'Step {n}: {msg}', flush=True)

try:
    step(1, 'Importing db modules...')
    from corvin.storage.db import get_engine, is_sqlite
    step(2, f'is_sqlite={is_sqlite()}')

    from corvin.storage.models import Base
    step(3, 'Base imported')

    if is_sqlite():
        Base.metadata.create_all(get_engine())
        step(4, 'DB tables created')

    from corvin.core.config_loader import get_env, load_config
    policy = load_config('policies/investigation', get_env())
    enabled = policy.get('predictive_background_enabled', True)
    step(5, f'Policy loaded, predictive_background_enabled={enabled}')

    from corvin.triggers.predictive import PredictiveMonitor
    step(6, 'PredictiveMonitor imported')

    pm = PredictiveMonitor()
    step(7, 'PredictiveMonitor instantiated OK')

    from corvin.slo.snapshot import run_forever as slo_run_forever
    step(8, 'slo_run_forever imported')

    step(9, 'ALL STARTUP STEPS PASSED')

except Exception:
    traceback.print_exc()
