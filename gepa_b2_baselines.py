import sys
sys.path.insert(0, '/Users/kevinchon/Documents/Research/KDKC/gepa/src')
from gepa.optimize_anything import optimize_anything, EngineConfig, GEPAConfig, ReflectionConfig
import subprocess, pathlib, shutil, tempfile, json

REFLECTION_LM = 'claude-opus-4-5-20251101'
MAX_CALLS = 20
B2_DIR = pathlib.Path('/Users/kevinchon/Documents/Research/KDKC/b3_tasks/b2_agent_harness')
B2_FILES = ['agent.py', 'tools.py', 'planner.py', 'harness.py']

def make_evaluator(mode):
    def evaluate(program):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = pathlib.Path(tmp)
            for f in B2_DIR.glob('*.py'):
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
                r = subprocess.run(['python3', 'evaluate.py'], capture_output=True, text=True, cwd=tmpdir, timeout=30)
                if r.returncode != 0: return 0.0
                return float(json.loads(r.stdout.strip().split('\n')[-1]).get('score', 0.0))
            except: return 0.0
    return evaluate

if __name__ == "__main__":
    import sys
    mode = sys.argv[1]
    if mode == 'perfile':
        seed = (B2_DIR / 'agent.py').read_text()
        ev = make_evaluator('agent.py')
        obj = "Modify agent.py to integrate the Planner so all 10 task types are handled correctly. Score is fraction solved (0.0-1.0)."
    else:
        parts = [f"### FILE: {f}\n{(B2_DIR/f).read_text()}" for f in B2_FILES]
        seed = '\n\n'.join(parts)
        ev = make_evaluator('concat')
        obj = "Optimize multi-file agent harness so all 10 tasks pass. Files use ### FILE: markers. Integrate Planner into Agent."
    optimize_anything(
        seed_candidate=seed, evaluator=ev, objective=obj,
        config=GEPAConfig(engine=EngineConfig(max_metric_calls=MAX_CALLS), reflection=ReflectionConfig(reflection_lm=REFLECTION_LM)),
    )
    print(f"B2 {mode} done")
