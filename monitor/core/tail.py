"""Incremental, tolerant JSONL reader: remembers a byte offset, only returns complete lines, reads in bounded chunks."""
import json
import os

CHUNK = 16 * 1024 * 1024


class Tail:
    def __init__(self, path):
        self.path = path
        self.off = 0
        self.ino = None
        self.bad = 0

    def read_new(self, cb=None):
        """Call cb(offset, length, obj) for every newly completed line (or return them as a list if cb is None).
        Resets if the file was replaced or shrunk. Memory use is bounded by CHUNK."""
        out = []
        sink = cb or (lambda off, ln, obj: out.append((off, ln, obj)))
        try:
            st = os.stat(self.path)
        except OSError:
            return out
        if self.ino is not None and (st.st_ino != self.ino or st.st_size < self.off):
            self.off = 0
        self.ino = st.st_ino
        size = st.st_size
        with open(self.path, "rb") as f:
            while self.off < size:
                f.seek(self.off)
                data = f.read(min(CHUNK, size - self.off))
                last_nl = data.rfind(b"\n")
                if last_nl < 0:
                    if len(data) >= CHUNK:          # a single line longer than a chunk: skip it rather than stall
                        self.off += len(data)
                        self.bad += 1
                        continue
                    break                           # half-written last line: wait for the next round
                pos = 0
                while pos <= last_nl:
                    nl = data.find(b"\n", pos)
                    raw = data[pos:nl]
                    if raw.strip():
                        try:
                            sink(self.off + pos, nl - pos + 1, json.loads(raw))
                        except Exception:
                            self.bad += 1
                    pos = nl + 1
                self.off += pos
        return out


def read_line_at(path, off, ln):
    with open(path, "rb") as f:
        f.seek(off)
        return json.loads(f.read(ln))
