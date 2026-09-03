"""GEPA baselines for B1 LRU+graph and B1 ML loop."""
import sys
sys.path.insert(0, '/Users/kevinchon/Documents/Research/KDKC/gepa/src')

from gepa.optimize_anything import optimize_anything, EngineConfig, GEPAConfig, ReflectionConfig
import subprocess, pathlib, shutil, tempfile, json

REFLECTION_LM = 'claude-opus-4-5-20251101'
MAX_CALLS = 20

LRU_DIR = pathlib.Path('/Users/kevinchon/Documents/Research/KDKC/b3_tasks/b1_lru_graph')
LRU_FILES = ['cache.py', 'graph.py', 'search.py', 'utils.py']
ML_DIR = pathlib.Path('/Users/kevinchon/Documents/Research/KDKC/b3_tasks/b1_ml_loop')
ML_FILES = ['model.py', 'data.py', 'loss.py', 'trainer.py']


def make_evaluator(task_dir, mode, score_key):
    def evaluate(program: str) -> float:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = pathlib.Path(tmp)
            for f in task_dir.glob('*.py'):
                shutil.copy(f, tmpdir / f.name)
            if mode == 'concat':
                current = None; lines = []
                for line in program.split('\n'):
                    if line.startswith('### FILE: '):
                        if current and lines:
                            (tmpdir / current).write_text('\n'.join(lines))
                        current = line.replace('### FILE: ', '').strip(); lines = []
                    else:
                        lines.append(line)
                if current and lines:
                    (tmpdir / current).write_text('\n'.join(lines))
            else:
                (tmpdir / mode).write_text(program)
            try:
                result = subprocess.run(['python3', 'evaluate.py'], capture_output=True, text=True, cwd=tmpdir, timeout=60)
                if result.returncode != 0: return 0.0
                last = result.stdout.strip().split('\n')[-1]
                return float(json.loads(last).get(score_key, 0.0))
            except Exception:
                return 0.0
    return evaluate


def run_task(name, task_dir, files, mode, seed_file, score_key, objective):
    print(f"\n=== {name} ===")
    if mode == 'concat':
        parts = [f"### FILE: {f}\n{(task_dir/f).read_text()}" for f in files]
        seed = '\n\n'.join(parts)
        ev = make_evaluator(task_dir, 'concat', score_key)
    else:
        seed = (task_dir / seed_file).read_text()
        ev = make_evaluator(task_dir, seed_file, score_key)
    result = optimize_anything(
        seed_candidate=seed, evaluator=ev, objective=objective,
        config=GEPAConfig(
            engine=EngineConfig(max_metric_calls=MAX_CALLS),
            reflection=ReflectionConfig(reflection_lm=REFLECTION_LM),
        ),
    )
    print(f"{name} done")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=['lru-perfile', 'lru-concat', 'ml-perfile', 'ml-concat'])
    args = p.parse_args()
    
    if args.mode == 'lru-perfile':
        run_task('B1 LRU per-file', LRU_DIR, LRU_FILES, 'cache.py', 'cache.py', 'queries_per_sec',
                 "Implement a real LRU cache to maximize queries per second on graph shortest-path lookups.")
    elif args.mode == 'lru-concat':
        run_task('B1 LRU concat', LRU_DIR, LRU_FILES, 'concat', None, 'queries_per_sec',
                 "Optimize multi-file graph search to maximize qps. Files use ### FILE: markers.")
    elif args.mode == 'ml-perfile':
        run_task('B1 ML per-file', ML_DIR, ML_FILES, 'model.py', 'model.py', 'samples_per_sec',
                 "Vectorize the MLP with NumPy to maximize training samples per second.")
    elif args.mode == 'ml-concat':
        run_task('B1 ML concat', ML_DIR, ML_FILES, 'concat', None, 'samples_per_sec',
                 "Optimize multi-file ML training to maximize samples per second. Files use ### FILE: markers.")
