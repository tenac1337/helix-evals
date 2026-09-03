"""
Patch core/batch_runner.py to fix the evaluate.py written into each HELIX project.

The original uses a subprocess wrapper (inner/outer pattern) that silently
swallows the score. This replaces it with a direct in-process call that
prints one clean JSON line — exactly what HELIX's json_score parser expects.

Run from helix-evals root:
    python patch_batch_runner.py
"""
import pathlib, sys

target = pathlib.Path("core/batch_runner.py")
if not target.exists():
    sys.exit(f"ERROR: {target} not found. Run from helix-evals root.")

src = target.read_text()

# The string we want to replace — the entire (proj/"evaluate.py").write_text(...) call
OLD = '''        (proj/"evaluate.py").write_text('import subprocess, sys, json, pathlib, tempfile, os\\n# Write inner script to temp file\\n_inner = "import json, pathlib, sys, io, traceback, warnings, os\\\\nwarnings.filterwarnings(\'ignore\')\\\\nos.environ[\'FRONTIER_CS_REPO\'] = \'/Users/kevinchon/Documents/Research/KDKC/Frontier-CS\'\\\\nsys.path.insert(0, \'/Users/kevinchon/Documents/Research/KDKC/helix-evals\')\\\\nfrom frontier_adapter import FrontierCSAdapter, FrontierTask\\\\nroot = pathlib.Path(__file__).parent\\\\nspec = json.loads((root/\'problem.json\').read_text())\\\\ncode = (root/\'solve.cpp\').read_text()\\\\n_real_stdout = sys.stdout\\\\nsys.stdout = io.StringIO()\\\\ntry:\\\\n    adapter = FrontierCSAdapter(backend=\'docker\')\\\\n    score, asi = adapter.evaluate(code, FrontierTask(\\\\n        track=spec[\'track\'], problem_id=spec[\'problem_id\'], language=\'cpp\'))\\\\n    _out = json.dumps({\'score\': score, \'instance_scores\': {str(spec[\'problem_id\']): score}, \'asi\': asi[:4000]})\\\\nexcept Exception as exc:\\\\n    _out = json.dumps({\'score\': 0.0, \'instance_scores\': {str(spec[\'problem_id\']): 0.0},\\\\n        \'error\': f\'{type(exc).__name__}: {exc}\', \'traceback\': traceback.format_exc()})\\\\nfinally:\\\\n    sys.stdout = _real_stdout\\\\nprint(_out)\\\\n"\\n_tmp = pathlib.Path(__file__).parent / "_inner_eval.py"\\n_tmp.write_text(_inner)\\nresult = subprocess.run(\\n    [\'/Users/kevinchon/Documents/Research/KDKC/helix-evals/.venv/bin/python3\', str(_tmp)],\\n    capture_output=True, text=True,\\n    cwd=str(pathlib.Path(__file__).parent)\\n)\\n# Find the JSON line in stdout\\nfor line in result.stdout.strip().splitlines():\\n    line = line.strip()\\n    if line.startswith(\'{"score"\\') or line.startswith(\'{"error"\\'):\\n        print(line)\\n        sys.exit(0)\\n# fallback\\nprint(json.dumps({"score": 0.0, "instance_scores": {}, "error": "no json found", "stdout": result.stdout[:500], "stderr": result.stderr[:500]}))\\n')'''

NEW = '''        (proj/"evaluate.py").write_text(
            "import json, pathlib, sys, traceback, warnings, os\\n"
            "warnings.filterwarnings('ignore')\\n"
            "os.environ['FRONTIER_CS_REPO'] = '/Users/kevinchon/Documents/Research/KDKC/Frontier-CS'\\n"
            "sys.path.insert(0, '/Users/kevinchon/Documents/Research/KDKC/helix-evals')\\n"
            "from frontier_adapter import FrontierCSAdapter, FrontierTask\\n"
            "root = pathlib.Path(__file__).parent\\n"
            "spec = json.loads((root/'problem.json').read_text())\\n"
            "code = (root/'solve.cpp').read_text()\\n"
            "try:\\n"
            "    adapter = FrontierCSAdapter(backend='docker')\\n"
            "    score, asi = adapter.evaluate(code, FrontierTask(\\n"
            "        track=spec['track'], problem_id=spec['problem_id'], language='cpp'))\\n"
            "    print(json.dumps({'score': score, 'instance_scores': {str(spec['problem_id']): score}, 'asi': asi[:4000]}))\\n"
            "except Exception as exc:\\n"
            "    print(json.dumps({'score': 0.0, 'instance_scores': {str(spec['problem_id']): 0.0},\\n"
            "        'error': f'{type(exc).__name__}: {exc}', 'traceback': traceback.format_exc()}))\\n"
        )'''

if OLD in src:
    patched = src.replace(OLD, NEW)
    target.write_text(patched)
    print("✓ Patched successfully.")
else:
    # Try a looser match — find the line and replace the whole write_text block
    lines = src.splitlines()
    start = None
    for i, line in enumerate(lines):
        if '(proj/"evaluate.py").write_text(' in line and '_inner' in line:
            start = i
            break

    if start is None:
        print("ERROR: Could not find the evaluate.py write_text block.")
        print("Apply the fix manually — replace the (proj/\"evaluate.py\").write_text(...) call")
        print("in _write_helix_project with:")
        print()
        print(NEW)
        sys.exit(1)

    # Find the end of the statement (the closing ')
    end = start
    for i in range(start, len(lines)):
        if lines[i].rstrip().endswith("')"):
            end = i
            break

    new_lines = lines[:start] + NEW.splitlines() + lines[end+1:]
    target.write_text("\n".join(new_lines) + "\n")
    print(f"✓ Patched lines {start}-{end} successfully.")

print("Run smoke test:")
print("  python track_c/run_frontier_cs.py --optimizer helix --helix-backend opencode --n-problems 3 --max-generations 2 --max-evaluations 4 --max-turns 10")
