#!/usr/bin/env python3
"""Replay real SGR mouse events through a release TUI's PTY, backend on/off.
Only the benchmark's own server is stopped. Results/trace live outside Git.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import threading
import statistics
import struct
import subprocess
import tempfile
import termios
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]

def pct(xs, p):
    return sorted(xs)[min(len(xs)-1, int(len(xs)*p))] if xs else 0

def run(binary, label, stop, output):
    server = subprocess.Popen([str(ROOT/'ml/.venv/bin/python'), '-m', 'osrs_ml.server', '--port', '8799'], cwd=ROOT/'ml', stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(150):
        try:
            urllib.request.urlopen('http://127.0.0.1:8799/api/health', timeout=1).read()
            break
        except Exception:
            time.sleep(.1)
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 55, 220, 0, 0))
    trace = output/f'{label}.jsonl'
    with tempfile.TemporaryDirectory() as config:
        env = dict(os.environ, TERM='xterm-256color', XDG_CONFIG_HOME=config, OSRS_TERM_TRACE=str(trace))
        proc = subprocess.Popen([binary, '--server', 'http://127.0.0.1:8799', '--view', 'market'], stdin=slave, stdout=slave, stderr=slave, env=env)
        os.close(slave)
        def reader():
            while True:
                try:
                    if select.select([master], [], [], .05)[0]: os.read(master,1048576)
                    if proc.poll() is not None: return
                except OSError: return
        threading.Thread(target=reader,daemon=True).start()
        def drain(seconds):
            if seconds>0: time.sleep(seconds)
        drain(5)
        if stop:
            server.terminate(); server.wait(timeout=20)
            drain(.5)
        def send(code, x, y, end='M'):
            os.write(master, f'\x1b[<{code};{x+1};{y+1}{end}'.encode())
        send(0, 20, 2)
        drain(.1)
        sent=[]
        start=time.time_ns()/1000
        # 1000 input events/s, 3s; each coordinate pair is unique within the replay.
        begin=time.monotonic()
        for i in range(3000):
            target=begin+i/1000
            while time.monotonic()<target:
                drain(min(.0002, target-time.monotonic()))
            x=20+(i%150); y=2+((i//150)%20)
            sent.append((time.time_ns()/1000, [x,y]))
            send(32,x,y)

        drain(5)
        send(0,20,2,'m'); drain(.2)
        os.write(master,b'q'); drain(.5)
        proc.wait(timeout=10)
    if server.poll() is None:
        server.terminate(); server.wait(timeout=20)
    os.close(master)
    rows=[json.loads(x) for x in trace.read_text().splitlines()]
    drag=[r for r in rows if r['drag'] and r['us']>=start and r['us']<=start+3_000_000]
    sent_map={tuple(pos):t for t,pos in sent}
    lag=[(r['us']-sent_map[tuple(r['pos'])])/1000 for r in rows if r['drag'] and tuple(r['pos'] or []) in sent_map and r['us']>=sent_map[tuple(r['pos'])]]
    queued=[]
    for r in drag:
        injected=sum(t<=r['us'] for t,_ in sent)
        queued.append(max(0,injected-(r['events']-1)))
    result=dict(label=label, injected_events_s=1000, processed_events_s=round((drag[-1]['events']-drag[0]['events'])/3,1), draws_s=round(len(drag)/3,1), draw_ms_p50=round(pct([r['draw_us']/1000 for r in drag],.5),3), draw_ms_p99=round(pct([r['draw_us']/1000 for r in drag],.99),3), bytes_frame_mean=round(statistics.mean(r['bytes'] for r in drag)), cursor_render_ms_p50=round(pct(lag,.5),3), cursor_render_ms_p99=round(pct(lag,.99),3), queue_events_max=max(queued), coalesced_batch_max=max(r['batch'] for r in drag))
    print(json.dumps(result),flush=True)
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--binary',default=str(ROOT/'tui/target/release/osrs-term')); parser.add_argument('--label',default='baseline'); parser.add_argument('--output',default='/tmp/osrs-drag')
    args=parser.parse_args(); output=Path(args.output); output.mkdir(exist_ok=True, parents=True)
    results=[run(args.binary,args.label+'-'+mode,mode=='offline',output) for mode in ['online','offline']]
    (output/f'{args.label}-summary.json').write_text(json.dumps(results,indent=2))
