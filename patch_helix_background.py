"""
Patches core/batch_runner.py to:
1. Load problem statement and pass it to _write_helix_project
2. Include problem statement in the HELIX agent background
3. Tell the agent to rewrite solve.cpp for the specific problem type

Run from helix-evals root:
    python patch_helix_background.py
"""
import pathlib, sys

target = pathlib.Path("core/batch_runner.py")
if not target.exists():
    sys.exit("ERROR: run from helix-evals root")

src = target.read_text()
patched = src

# ── Fix 1: pass stmt_text to _write_helix_project ──────────────────────────
old1 = "        self._write_helix_project(proj, problem_id, adapter_dir)"
new1 = (
    "        _stmt_path = pathlib.Path(os.environ.get('FRONTIER_CS_REPO', '../Frontier-CS')) / 'algorithmic' / 'problems' / str(problem_id) / 'statement.txt'\n"
    "        _stmt_text = _stmt_path.read_text()[:4000] if _stmt_path.exists() else f'Problem {problem_id}'\n"
    "        self._write_helix_project(proj, problem_id, adapter_dir, _stmt_text)"
)
if old1 in patched:
    patched = patched.replace(old1, new1)
    print("✓ Fix 1: pass stmt_text")
else:
    print("✗ Fix 1 not found")

# ── Fix 2: update _write_helix_project signature ───────────────────────────
old2 = "    def _write_helix_project(self, proj, problem_id, adapter_dir):"
new2 = "    def _write_helix_project(self, proj, problem_id, adapter_dir, stmt_text=''):"
if old2 in patched:
    patched = patched.replace(old2, new2)
    print("✓ Fix 2: signature")
else:
    print("✗ Fix 2 not found")

# ── Fix 3: replace background string ───────────────────────────────────────
old3 = 'background = "You are improving a C++ solution for a competitive programming problem. Only modify solve.cpp. Read problem.json to understand the problem. Read evaluate.py to understand scoring. The goal is to maximize the score by improving the algorithm - better approaches, smarter logic, optimized output format. Use Bash to compile with: g++ -std=c++17 -O2 -o sol solve.cpp and test it. Make substantial algorithmic improvements, not just refactoring."'

# Build the new background as a Python expression that will be evaluated
# inside the list that _write_helix_project joins with "\n"
new3 = (
    'f\'background = """\'\n'
    "            f'You are solving competitive programming problem {problem_id}.\\n'\n"
    "            f'\\nPROBLEM STATEMENT:\\n{stmt_text[:3000]}\\n'\n"
    "            '\\nINSTRUCTIONS:\\n'\n"
    "            '- Only modify solve.cpp\\n'\n"
    "            '- Compile: g++ -std=c++17 -O2 -o sol solve.cpp\\n'\n"
    "            '- The current solve.cpp may be for a DIFFERENT problem. Rewrite it completely for THIS problem.\\n'\n"
    "            '- Any valid output scores > 0. Start simple, get valid output first.\\n'\n"
    "            '- Compile and test your solution before finishing.\\n'\n"
    "            '- Output [MUTATION COMPLETE] when done.\\n'\n"
    '            f\'\"\"\"'
)

if old3 in patched:
    patched = patched.replace(old3, new3)
    print("✓ Fix 3: background string")
else:
    print("✗ Fix 3 not found — showing nearby lines:")
    lines = patched.splitlines()
    for i, l in enumerate(lines):
        if 'background' in l and 'solve.cpp' in l:
            for j in range(max(0,i-2), min(len(lines),i+3)):
                print(f"  {j+1}: {repr(lines[j][:100])}")

target.write_text(patched)
print("\nDone. Test with: python track_c/run_frontier_cs.py --optimizer helix --helix-backend opencode --n-problems 1 --max-generations 1 --max-evaluations 2 --max-turns 15 --no-resume")
