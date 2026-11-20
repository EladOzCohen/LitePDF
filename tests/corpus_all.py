"""Run corpus_one.py on every PDF in the given folders (each in its own process with a timeout)."""
import glob, json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
pdfs = []
for folder in sys.argv[2:]:
    pdfs += glob.glob(os.path.join(folder, "**", "*.pdf"), recursive=True)
pdfs = [p for p in pdfs if "claude_projects" not in p and os.path.getsize(p) < 400 * 1024 * 1024]
print(len(pdfs), "pdfs")
bad = 0
for p in sorted(pdfs):
    try:
        r = subprocess.run([sys.executable, "-X", "utf8", os.path.join(HERE, "corpus_one.py"), p], capture_output=True, text=True, timeout=int(sys.argv[1]))
        line = [l for l in r.stdout.splitlines() if l.startswith("{")]
        if not line:
            print("CRASH/NO-OUTPUT", os.path.basename(p), "rc", r.returncode, r.stderr[-300:].replace("\n", " ")); bad += 1; continue
        j = json.loads(line[-1])
        flag = "OK " if not j["errors"] and not j.get("failed_checks") else "BAD"
        if flag == "BAD": bad += 1
        print(flag, j["file"][:48].ljust(48), f"{j['kb']}KB pages={j.get('pages')} open={j.get('open_s')}s words/page={j.get('words_on_page')} scr={j.get('scrambled')} rot={j.get('rotations')} save={j.get('save')} fail={j.get('failed_checks')} {j['notes']}")
        for e in j["errors"]: print("    ERROR:", e.replace("\n", " | ")[-400:])
    except subprocess.TimeoutExpired:
        print("TIMEOUT", os.path.basename(p)); bad += 1
print("problems:", bad)
