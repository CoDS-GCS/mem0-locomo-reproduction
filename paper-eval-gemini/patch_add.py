"""Make add.py wait longer between retries (rate limits on Vertex AI): 6 tries, waiting 2, 4, 8, 16, 32 s.
Run once from paper-eval-gemini:  python patch_add.py
"""
p = "src/memzero/add.py"
s = open(p).read()

old_sig = "def add_memory(self, user_id, message, metadata, retries=3):"
old_sleep = "time.sleep(1)  # Wait before retrying"
if "retries=6):" in s and "2 ** (attempt + 1)" in s:
    print("already patched")
else:
    assert s.count(old_sig) == 1, f"signature found {s.count(old_sig)} times - stop and tell Claude"
    assert s.count(old_sleep) == 1, f"sleep line found {s.count(old_sleep)} times - stop and tell Claude"
    s = s.replace(old_sig, old_sig.replace("retries=3", "retries=6"))
    s = s.replace(old_sleep, "time.sleep(min(60, 2 ** (attempt + 1)))  # backoff: 2, 4, 8, 16, 32 s")
    open(p, "w").write(s)
    print("add.py patched OK")

for needed in ("END_CONV", "SKIPPED BATCH", "Messages added successfully"):
    print(f"  contains {needed!r}: {needed in s}")
