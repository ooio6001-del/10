"""Local-only SOLSTRATS MILLION read-only market watcher and paper simulator."""
import json, os, threading, time, urllib.request, urllib.error
from collections import defaultdict, deque
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from engine import PaperAccount, config_at, TOTAL_CONFIGURATIONS, should_enter, should_exit

BASE=Path(__file__).resolve().parent
DATA=BASE/"state"
DATA.mkdir(exist_ok=True)
STATEFILE=DATA/"session.json"
PORT=int(os.environ.get("SOLSTRATS_PORT","8792"))
POLL_SECONDS=45
MAX_PAIRS=8
ACTIVE_STRATEGIES=100
lock=threading.RLock()
running=True
status="starting"
last_error=""
last_update=None
last_source=None
observations=defaultdict(lambda:deque(maxlen=250))
pairs={}
accounts={}
evaluations=0
paper_events=deque(maxlen=150)
started=time.time()

def read_json(url):
    req=urllib.request.Request(url,headers={"User-Agent":"SOLSTRATS-MILLION/0.1 (+paper-only)","Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=12) as resp:
        return json.loads(resp.read(1_000_000).decode("utf-8"))

def save():
    with lock:
        payload={"saved_at":time.time(),"last_update":last_update,"evaluations":evaluations,
                 "accounts":{str(i):vars(a) for i,a in accounts.items()},
                 "events":list(paper_events)}
    tmp=STATEFILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload),encoding="utf-8")
    tmp.replace(STATEFILE)

def restore():
    global evaluations,last_update
    if not STATEFILE.exists():
        return
    try:
        payload=json.loads(STATEFILE.read_text(encoding="utf-8"))
        evaluations=int(payload.get("evaluations",0))
        last_update=payload.get("last_update")
        for k,v in payload.get("accounts",{}).items():
            if int(k)>=ACTIVE_STRATEGIES: continue
            fields=PaperAccount.__dataclass_fields__
            accounts[int(k)]=PaperAccount(**{key:val for key,val in v.items() if key in fields})
        paper_events.extend(payload.get("events",[])[-150:])
    except (OSError,ValueError,TypeError) as exc:
        print("Previous session could not be loaded:",exc)

def fetch_pairs():
    # Token boosts yield discovery candidates; the second endpoint verifies actual Solana pairs.
    discovered=read_json("https://api.dexscreener.com/token-boosts/latest/v1")
    addresses=[]
    for item in discovered if isinstance(discovered,list) else []:
        if item.get("chainId")=="solana" and item.get("tokenAddress"):
            address=item["tokenAddress"]
            if address not in addresses: addresses.append(address)
        if len(addresses)>=5: break
    output={}
    for address in addresses:
        try:
            results=read_json("https://api.dexscreener.com/latest/dex/tokens/"+address)
            candidates=[p for p in (results.get("pairs") or []) if p.get("chainId")=="solana"]
            candidates.sort(key=lambda p:float((p.get("liquidity") or {}).get("usd") or 0),reverse=True)
            if candidates:
                p=candidates[0]
                price=float(p.get("priceUsd") or 0)
                liquidity=float((p.get("liquidity") or {}).get("usd") or 0)
                if price>0 and liquidity>=5000:
                    output[address]={"name":str((p.get("baseToken") or {}).get("name") or address[:8])[:60],
                       "symbol":str((p.get("baseToken") or {}).get("symbol") or "?")[:18],
                       "address":address,"price":price,"liquidity":liquidity,
                       "volume5m":float((p.get("volume") or {}).get("m5") or 0),
                       "url":p.get("url") or ""}
        except (OSError,ValueError,TypeError,KeyError): continue
        if len(output)>=MAX_PAIRS: break
    return output

def tick():
    global last_update,last_source,evaluations,status,last_error,pairs
    fresh=fetch_pairs()
    if not fresh: raise ValueError("No eligible Solana pairs returned from free endpoint")
    now=time.time()
    with lock:
        pairs=fresh
        last_update=now
        last_source="DEX Screener free API"
        status="live"
        last_error=""
        for address,p in fresh.items():
            rows=observations[address]
            rows.append((now,p["price"],p["volume5m"]))
            if len(rows)<3: continue  # require actual sampled observations
            past=rows[max(0,len(rows)-3)][1]
            if past<=0: continue
            change=100*(p["price"]/past-1)
            oldvol=rows[max(0,len(rows)-3)][2]
            volume_ratio=p["volume5m"]/max(1.0,oldvol)
            # Only one observed token per account at a time; one shared price observation
            # drives all bounded paper strategies, rather than one API request per strategy.
            for i in range(ACTIVE_STRATEGIES):
                c=config_at(i*10000)
                a=accounts.setdefault(i,PaperAccount())
                if a.units and a.token != address:
                    continue  # Never mark or sell a position using a different token price
                if a.units:
                    if should_exit(c,a,p["price"],now):
                        a.sell(p["price"],now)
                        paper_events.appendleft({"ts":now,"strategy":i,"side":"SELL","symbol":p["symbol"],"balance":round(a.cash,5)})
                elif should_enter(c,change,volume_ratio):
                    if a.buy(p["price"],now):
                        a.token=address
                        paper_events.appendleft({"ts":now,"strategy":i,"side":"BUY","symbol":p["symbol"],"balance":round(a.cash,5)})
                a.mark(p["price"])
                evaluations+=1
    save()

def worker():
    global status,last_error
    restore()
    while True:
        with lock:
            enabled=running
        if enabled:
            try: tick()
            except (OSError,ValueError,TypeError,KeyError) as exc:
                with lock:
                    status="unavailable"
                    last_error=str(exc)[:200]
        time.sleep(POLL_SECONDS if enabled else 2)

def snapshot():
    with lock:
        ranked=sorted(({"id":i*10000,"family":config_at(i*10000)["family"],"equity":round(a.last_equity,4),
                         "realized":round(a.realized,4),"trades":a.trades,
                         "wins":a.wins,"drawdown":round(a.max_drawdown_pct,2)} for i,a in accounts.items()),
                      key=lambda row:(row["equity"],row["trades"]),reverse=True)[:100]
        return {"running":running,"source_status":status,"error":last_error,"updated":last_update,
            "source":last_source,"uptime":round(time.time()-started),
            "total_configurations":TOTAL_CONFIGURATIONS,"active_configurations":ACTIVE_STRATEGIES,
            "paper_signal_evaluations":evaluations,"completed_backtests":0,
            "pairs":list(pairs.values()),"leaders":ranked,"events":list(paper_events)[:30],
            "notice":"LIVE market observations. PAPER trades only. No real orders; estimated fills and costs."}

class Handler(BaseHTTPRequestHandler):
    def reply(self,data,code=200):
        encoded=json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store")
        self.send_header("Content-Length",str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)
    def do_GET(self):
        if self.path=="/api/status": return self.reply(snapshot())
        if self.path in ("/","/index.html"):
            body=(BASE/"dashboard"/"index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type","text/html; charset=utf-8")
            self.send_header("Content-Length",str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        self.reply({"error":"Not found"},404)
    def do_POST(self):
        global running,status
        if self.path not in ("/api/start","/api/pause","/api/stop"):
            return self.reply({"error":"Not found"},404)
        with lock:
            running=self.path=="/api/start"
            status="starting" if running else "paused"
        self.reply({"ok":True,"running":running})
    def log_message(self,fmt,*args):
        if not self.path.startswith("/api/status"): super().log_message(fmt,*args)

if __name__=="__main__":
    threading.Thread(target=worker,daemon=True).start()
    server=ThreadingHTTPServer(("127.0.0.1",PORT),Handler)
    print("SOLSTRATS MILLION: http://127.0.0.1:%d"%PORT)
    print("Read-only market data / paper trading only. Ctrl+C to exit.")
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        server.server_close()
        save()
