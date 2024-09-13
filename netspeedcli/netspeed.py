from pathlib import Path
from typing import Optional

import typer
import time
import random
import requests
import psutil
import ping3
import json
import threading

from typing_extensions import Annotated
from importlib import resources
from urllib.parse import urlparse
from .servers import SERVERS

app = typer.Typer(add_completion=False)

__version__ = "0.1.0"

class NetSpeedTest:

    def __init__(self, server: str, settings: dict) -> None:
        self.totLoaded = 0
        self.startT = 0        
        self.rlist = []
        self.tlist = []
        self.finish = threading.Event()
        self.server = server
        self.settings = settings


    def clearRequests(self):
        for req in self.rlist:
            req.close()
        self.rlist = []
        return


    def dataStream(self, data, chunkSize=1024):
        totSize = len(data)
        for i in range(0, totSize, chunkSize):
            yield data[i:i + chunkSize]


    def printProgress(self):
            visualProgress = round(50 * self.Progress)
            statusStr = f"Speed: {self.Status:.2f} Mbps" if self.Status else ""
            print(f"\rProgress:[{'#' * visualProgress + ' ' * (50 - visualProgress)}] {100 * self.Progress:.2f}% {statusStr}   ", end="")


    def updateStatus(self, download: bool, multi: bool):
        mulKey = "multi" if multi else "single"
        dlKey = "download" if download else "upload"
        factor = self.settings["overhead_compensation_factor"] if multi else 1
        t = time.time() - self.startT
        if self.graceTimeDone:
            speed = self.totLoaded / t
            if multi and self.settings["auto_time_reduce"]:
                self.bonusT += min(6.4 * speed / 1e8, 0.8)
            self.Status = 8 * speed * factor / 1e6
            if multi:
                self.Progress = min(1, (t + self.bonusT) / self.settings[f"{mulKey}_{dlKey}_max_time"])
            else:
                self.Progress = min(1, self.totLoaded / (self.settings[f"{mulKey}_{dlKey}_package_size"] * 1e6))
                if self.finish.is_set():
                    self.Progress = 1
                    self.finish.clear()
                    return                                

            if t + self.bonusT > self.settings[f"{mulKey}_{dlKey}_max_time"]:              
                if multi:
                    self.Progress = 1
                    self.printProgress()
                    print("\nClosing Requests...")
                    self.finish.set()
                    self.clearRequests() #PERF: low performance
                    # threading.Thread(target=self.clearRequests)
                else:
                    self.timeExceed = True
                    print("\nTime Exceeded. Link Aborted.")
                return
            else:
                self.printProgress()
                threading.Timer(self.settings[f"{dlKey}_update_interval"], self.updateStatus, (download, multi)).start()

        elif t > self.settings[f"{dlKey}_gracetime"]:
            self.graceTime = t
            self.startT = time.time()
            self.totLoaded = self.bonusT = 0
            self.graceTimeDone = True
            threading.Timer(self.settings[f"{dlKey}_update_interval"], self.updateStatus, (download, multi)).start()
        else:
            threading.Timer(0.2, self.updateStatus, (download, multi)).start()


    def ipTest(self):
        self.startT = time.time()
        url = "https://api.ipify.org"
        kw = {"format": "json"}

        print("Ip Test Started")

        response = requests.get(url, params= kw, timeout= 10)
        ip_adr = response.json()["ip"]
        response.close()
        print(f"Ip Adress: {ip_adr}, took {time.time() - self.startT:.2f}s")


    def pingTest(self, hostName: Optional[str]=None):
        self.Progress = 0
        self.Status = ""
        self.startT = time.time()

        url = hostName if hostName else self.server.replace("/","").replace("https:","")    
        loss = 0
        prevPing = 0
        avgPing = None
        jitter = None
        print("Ping Test Started")

        for i in range(self.settings["ping_test_times"]):
            self.Progress = i / self.settings["ping_test_times"]
            curPing = ping3.ping(url, timeout=self.settings["ping_wait_time"])
            if curPing:
                curPing *= 1000
                if curPing < 1:
                    curPing = avgPing if avgPing else 1
                if avgPing is None:
                    avgPing = curPing
                else:
                    avgPing = curPing if curPing < avgPing else 0.8 * avgPing + 0.2 * curPing
                    curJitter = abs(curPing - prevPing)
                    if jitter is None:
                        jitter = curJitter
                    else:
                        jitter = 0.3 * jitter + 0.7 * curJitter if curJitter < jitter else 0.8 * jitter + 0.2 * curJitter
                prevPing = curPing    
            else:    
                loss += 1            
            lossRate = 100 * loss / self.settings["ping_test_times"]
            self.printProgress()
        
        self.Progress = 1
        self.printProgress()
        print(f"\nPing: {avgPing:.2f} ms, Jitter: {jitter:.2f} ms, Packet Loss Rate: {lossRate:.2f}%, took {time.time() - self.startT:.2f}s")


    def singleDLTest(self):
        self.finish.clear()
        self.Status = ""
        self.Progress = 0
        self.totLoaded = 0
        self.graceTimeDone = True
        self.graceTime = 0
        self.bonusT = 0
        self.timeExceed = False        

        print("Single-Stream Download Test Started")

        r = random.random()
        kw = {"r": r, "ckSize": self.settings["single_download_package_size"]}
        url = self.server + "garbage.php"
        self.startT = time.time()

        try:
            response = requests.get(url, params=kw, stream=True, timeout=10)
        except:
            print("Cannot link to the server")
            raise typer.Abort()

        inv = threading.Timer(0.5, self.updateStatus, (True, False))
        inv.start()
        for chunk in response.iter_content(chunk_size=self.settings["download_chunk_size"]):
            if chunk:
                self.totLoaded += len(chunk)
            if self.timeExceed:
                break

        endT = time.time()
        response.close()
        if not self.timeExceed:
            self.finish.set()
            time.sleep(1)
                
        t = endT - self.startT
        self.Status = 8 * self.totLoaded / (t * 1e6)
        self.printProgress()
        print(f"\nSingle Strem Download Speed: {self.Status:.2f} Mbps, took {t:.2f}s")


    def multiDLTest(self):
        self.finish.clear()
        self.Status = ""
        self.totLoaded = 0
        self.bonusT = 0
        self.graceTime = 0
        self.graceTimeDone = False
        self.Progress = 0
        self.startT = time.time()

        print("Multi-Stream Download Test Started")

        def testStream(i, delay):
            time.sleep(delay / 1000)
            url = self.server + "garbage.php"
            r = random.random()
            kw = {"r": r, "ckSize": self.settings["multi_download_package_size"]}

            # print(f"dl test stream started {i}")
            try:
                req = requests.get(url=url, stream=True, params=kw, timeout=10)
                self.rlist.append(req)                
                for chunk in req.iter_content(chunk_size=self.settings["download_chunk_size"]): 
                    #PERF: slow update causing low performance when closing requests
                    if self.finish.is_set():
                        req.close()
                        return
                    else:
                        loadDiff = len(chunk)
                        if loadDiff > 0:
                            self.totLoaded += loadDiff
                req.close()
                # print(f"dl stream finished {i}")
                testStream(i, 0)
            except:
                # print(f"dl stream failed {i}")
                testStream(i, 0)
        
        for i in range(self.settings["download_max_stream"]):
            dth = threading.Thread(target=testStream, args=(i, self.settings["download_multistream_delay"] * i), name=f"dllink{i}")
            dth.start()
            self.tlist.append(dth)

        inv = threading.Timer(self.settings["download_gracetime"], self.updateStatus, (True, True))
        inv.start()
        for t in self.tlist:
            t.join()
        self.tlist = []
        print("Done")
        print(f"Multi Strem Download Speed: {self.Status:.2f} Mbps, took {time.time() + self.graceTime - self.startT:.2f}s")

    def singleULTest(self):
        self.finish.clear()
        self.Status = ""
        self.Progress = 0
        self.totLoaded = 0
        self.graceTimeDone = True
        self.graceTime = 0
        self.bonusT = 0
        self.timeExceed = False        

        print("Single-Stream Upload Test Started")
        print("Might for a while, please waiting...") #BUG: stream dpesn't work

        r = random.random()
        kw = {"r": r}
        headers = {'Content-Encoding': 'identity', 'Content-Type': 'application/octet-stream'}
        url = self.server + "empty.php"
        data = b'\0' * self.settings["single_upload_package_size"] * 1024**2
        stream = self.dataStream(data, chunkSize=self.settings["upload_chunk_size"])
        self.startT = time.time()

        try:
            response = requests.post(url=url, data=data, params=kw, headers=headers, timeout=20)
        except:
            print("Cannot link to the server")
            raise typer.Abort()

        inv = threading.Timer(0.5, self.updateStatus, (False, False))
        inv.start()
        for chunk in stream:
            if chunk:
                self.totLoaded += len(chunk)
            if self.timeExceed:
                break

        endT = time.time()
        response.close()
        if not self.timeExceed:
            self.finish.set()
            time.sleep(1)
                
        t = endT - self.startT
        self.Status = 8 * self.totLoaded / (t * 1e6)
        self.printProgress()
        print(f"\nSingle Strem Upload Speed: {self.Status:.2f} Mbps, took {t:.2f}s")

    def multiULTest(self):
        self.finish.clear()
        self.Status = ""
        self.totLoaded = 0
        self.bonusT = 0
        self.graceTime = 0
        self.graceTimeDone = False
        self.Progress = 0
        self.startT = time.time()

        print("Multi-Stream Upload Test Started")

        def testStream(i, delay):
            time.sleep(delay / 1000)
            url = self.server + "empty.php"
            r = random.random()
            kw = {"r": r}
            headers = {'Content-Encoding': 'identity', 'Content-Type': 'application/octet-stream'}
            
            data = b'\0' * self.settings["multi_upload_package_size"] * 1024**2
            stream = self.dataStream(data, chunkSize=self.settings["upload_chunk_size"])
            
            # print(f"ul test stream started {i}")
            try:
                req = requests.post(url=url, data=data, stream=True, params=kw, headers=headers, timeout=10)
                self.rlist.append(req)                
                for chunk in stream:
                    if self.finish.is_set():
                        req.close()
                        return
                    else:
                        loadDiff = len(chunk)
                        if loadDiff > 0:
                            self.totLoaded += loadDiff
                req.close()
                # print(f"ul stream finished {i}")
                testStream(i, 0)
            except:
                # print(f"ul stream failed {i}")
                testStream(i, 0)
        
        for i in range(3):
            dth = threading.Thread(target=testStream, args=(i, self.settings["upload_multistream_delay"] * i), name=f"ullink{i}")
            dth.start()
            self.tlist.append(dth)
        
        inv = threading.Timer(self.settings["upload_gracetime"], self.updateStatus, (False, True))
        inv.start()
        for t in self.tlist:
            t.join()
        self.tlist = []
        print("Done")
        print(f"Multi Strem Upload Speed: {self.Status:.2f} Mbps, took {time.time() + self.graceTime - self.startT:.2f}s")
    
    def monitorSpeed(self, times: int =10, inv: float=1):
        print("Current Network Monitor Started")
        for i in range(times):
            oldSent = psutil.net_io_counters().bytes_sent 
            oldRecv = psutil.net_io_counters().bytes_recv
            time.sleep(inv)
            newSent = psutil.net_io_counters().bytes_sent 
            newRecv = psutil.net_io_counters().bytes_recv
            sent = 8 * (newSent - oldSent) / 1e6
            recv = 8 * (newRecv - oldRecv) / 1e6
            print(f"[{i+1}/{times}]: Current Sent Speed: {sent:.2f} Mbps, Current Receive Speed: {recv:.2f} Mbps")



def version_callback(v: bool):
    if v:
        print(__version__)
        raise typer.Exit()

def settings_callback(p: Optional[Path]):
    if p is None:
        return p
    if not p.exists():
        raise typer.BadParameter(f"{p.name} not exists")
    if p.is_dir() or ".json" not in p.name:
        raise typer.BadParameter(f"{p.name} must be a .json file")
    return p.resolve()

def server_callback(txt: str):
    s = txt.lower()
    if s == "auto" or s == "prev":
        return str(s)
    elif s not in SERVERS.keys():
        oplist = []
        for i in range(0, len(SERVERS.keys()), 2):
            oplist.append(f"{list(SERVERS.keys())[i].title()}, {list(SERVERS.keys())[i+1].upper()}")
        raise typer.BadParameter("Server not found\nthe server must be one of the followings:\n" + ",\n".join(oplist))
    else:
        print(f"Chosen Server: {s.upper() if len(s) <= 3 else s.title()}")
        return SERVERS[s]

def url_callback(u: Optional[str]):
    if u is None:
        return None
    hn = urlparse(u).hostname
    if hn is None:
        hostl = [part for part in u.split("/") if "." in part]
        if len(hostl) > 0 and ping3.ping(hostl[0]):
            return hostl[0].split(":")[0]
        hostl = [part for part in u.split("/") if "localhost" in part or len(part.split(".")) == 4]
        if len(hostl) == 1:
            return hostl[0].split(":")[0]
        raise typer.BadParameter("Invalid URL")
    else:
        return hn
    
def multiOnly(ctx: typer.Context, param: typer.CallbackParam, value):
    if ctx.params.get("mode") is not False or value is None or param.name not in ["graceTime", "maxStream", "delay"]:   
        return value
    raise typer.BadParameter(f"Option {param.name} can be only used in multi-stream test")
    

def autoServer():
    minServer = None
    minPing = 1000

    print("Auto selecting servers. Please wait a minute...")
    for i in range(0, len(SERVERS.keys()), 2):
        url = list(SERVERS.values())[i].replace("/","").replace("https:","")
        ping = ping3.ping(url, timeout=1)
        if ping and ping < minPing:
            minPing = ping
            minServer = list(SERVERS.keys())[i]
        time.sleep(0.2)

    if minServer:
        print(f"Auto-selected Server: {minServer.title()}")
        return minServer
    else:
        print("None of the servers are accessible")
        raise typer.Abort()

def getSS(server: str="noneed", settingsPath: Optional[Path]=None, record: bool=False):
    default = settingsPath is None
    if default:
        with resources.open_text("netspeedcli", "settings.json") as f:
            settings = json.load(f)
    else:
        with settingsPath.open(mode="r") as f:
            settings = json.load(f)
    if server == "noneed":
        return "", settings
    elif server == "prev" and settings["prev_server"]:
        sv = settings["prev_server"]
        print(f"Chosen Server: {sv}")
        return SERVERS[sv.lower()], settings
    elif server == "auto" or server == "prev":
        autoS = autoServer()
        if record or server == "prev":
            if default:
                print("Warning: Server will not be record in the default settings file.")
            else:
                settings["prev_server"] = autoS.title()
                with settingsPath.open(mode="w") as f:
                    json.dump(settings, f, indent=4, ensure_ascii=False)
        return SERVERS[autoS], settings
    elif record:
        if default:
            print("Warning: Server will not be record in the default settings file.")
        else:
            for k, v in SERVERS.items():
                if v == server: 
                    if k != settings["prev_server"].lower():
                        settings["prev_server"] = k.title()
                        with settingsPath.open(mode="w") as f:
                            json.dump(settings, f, indent=4, ensure_ascii=False)
                    break
    return server, settings
    

def curSettings(settings: dict, name: str, value):
    if value is not None:
        settings[name] = value
    return settings      


@app.command()
def ip():
    sv, st = getSS()
    test = NetSpeedTest(sv, st)
    test.ipTest()


@app.command()
def ping(
    url: Annotated[Optional[str], typer.Argument(callback=url_callback)] = None,
    settingsPath: Annotated[Optional[Path], typer.Option("--settings", "-s", envvar="AKM_SPEEDTEST_SETTINGS", show_envvar=False,
                                                callback=settings_callback)] = None ,
    server: Annotated[str, typer.Option("--server", "-v", callback=server_callback)] = "prev",
    record: Annotated[bool, typer.Option("--record", "-r")] = False,
    times: Annotated[Optional[int], typer.Option("--times", "-t")] = None,
    wait: Annotated[Optional[int], typer.Option("--wait", "-w")] = None
):
    if url is None:
        sv, st = getSS(server, settingsPath, record)
    else:
        print("Warning: Url selected. Server ping test cancelled.\nThe option --settings --server/s --record/-r will not work.")
        sv, st = getSS()
    curSettings(st, "ping_test_times", times)
    curSettings(st, "ping_wait_time", wait)
    test = NetSpeedTest(sv, st)
    test.pingTest(url)
    

@app.command()
def download(
    settingsPath: Annotated[Optional[Path], typer.Option("--settings", "-s", envvar="AKM_SPEEDTEST_SETTINGS", show_envvar=False,
                                                callback=settings_callback)] = None ,
    server: Annotated[str, typer.Option("--server", "-v", callback=server_callback)] = "prev",
    record: Annotated[bool, typer.Option("--record", "-r")] = False,
    mode: Annotated[bool, typer.Option("--multi/--single", "-m/-l")] = True,
    maxTime: Annotated[Optional[int], typer.Option("--max-time", "-t")] = None,
    timeReduce: Annotated[Optional[bool], typer.Option("--time-reduce/--full-time", "-r/-f")] = None,
    graceTime: Annotated[Optional[float], typer.Option("--grace-time", "-g", callback=multiOnly)] = None,
    maxStream: Annotated[Optional[int], typer.Option("--max-stream", "-x", callback=multiOnly)] = None,
    delay: Annotated[Optional[int], typer.Option("--delay", "-d", callback=multiOnly)] = None,
    interval: Annotated[Optional[float], typer.Option("--interval", "-i")] = None,
    package: Annotated[Optional[int], typer.Option("--package", "-p")] = None,
    chunk: Annotated[Optional[int], typer.Option("--chunk", "-c")] = None
):
    key = "multi" if mode else "single"
    sv, st = getSS(server, settingsPath, record)
    curSettings(st, f"{key}_download_max_time", maxTime)
    curSettings(st, "auto_time_reduce", timeReduce)
    curSettings(st, "download_gracetime", graceTime)
    curSettings(st, "download_max_stream", maxStream)
    curSettings(st, "download_multistream_delay", delay)
    curSettings(st, "download_update_interval", interval)
    curSettings(st, f"{key}_download_package_size", package)
    curSettings(st, "download_chunk_size", chunk)
    test = NetSpeedTest(sv, st)
    if mode:
        test.multiDLTest()
    else:
        test.singleDLTest()


@app.command()
def upload(
    settingsPath: Annotated[Optional[Path], typer.Option("--settings", "-s", envvar="AKM_SPEEDTEST_SETTINGS", show_envvar=False,
                                                callback=settings_callback)] = None ,
    server: Annotated[str, typer.Option("--server", "-v", callback=server_callback)] = "prev",
    record: Annotated[bool, typer.Option("--record", "-r")] = False,
    mode: Annotated[bool, typer.Option("--multi/--single", "-m/-l")] = True,
    maxTime: Annotated[Optional[int], typer.Option("--max-time", "-t")] = None,
    timeReduce: Annotated[Optional[bool], typer.Option("--time-reduce/--full-time", "-r/-f")] = None,
    graceTime: Annotated[Optional[float], typer.Option("--grace-time", "-g", callback=multiOnly)] = None,
    maxStream: Annotated[Optional[int], typer.Option("--max-stream", "-x", callback=multiOnly)] = None,
    delay: Annotated[Optional[int], typer.Option("--delay", "-d", callback=multiOnly)] = None,
    interval: Annotated[Optional[float], typer.Option("--interval", "-i")] = None,
    package: Annotated[Optional[int], typer.Option("--package", "-p")] = None,
    chunk: Annotated[Optional[int], typer.Option("--chunk", "-c")] = None
):
    key = "multi" if mode else "single"
    sv, st = getSS(server, settingsPath, record)
    curSettings(st, f"{key}_upload_max_time", maxTime)
    curSettings(st, "auto_time_reduce", timeReduce)
    curSettings(st, "upload_gracetime", graceTime)
    curSettings(st, "upload_max_stream", maxStream)
    curSettings(st, "upload_multistream_delay", delay)
    curSettings(st, "upload_update_interval", interval)
    curSettings(st, f"{key}_upload_package_size", package)
    curSettings(st, "upload_chunk_size", chunk)
    test = NetSpeedTest(sv, st)
    if mode:
        test.multiULTest()
    else:
        test.singleULTest()


@app.command()
def monitor(
    times: Annotated[int, typer.Option("--times", "-t")] = 10,
    interval: Annotated[float, typer.Option("--interval", "-i")] = 1
):
    sv, st = getSS()
    test = NetSpeedTest(sv, st)
    test.monitorSpeed(times, interval)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    settingsPath: Annotated[Optional[Path], typer.Option("--settings", "-s", envvar="AKM_SPEEDTEST_SETTINGS", show_envvar=False,
                                               callback=settings_callback)] = None ,
    server: Annotated[str, typer.Option("--server", "-v", callback=server_callback)] = "prev",
    record: Annotated[bool, typer.Option("--record", "-r")] = False,
    _: Annotated[Optional[bool], typer.Option("--version", callback=version_callback, is_eager=True)] = None
):
    if ctx.invoked_subcommand is None:
        sv, st = getSS(server, settingsPath, record)
        test = NetSpeedTest(sv, st)
        test.ipTest()
        test.pingTest()
        test.multiDLTest()
        test.multiULTest()
    elif record or server != "prev" or settingsPath is not None:
        print(f"Warning: The options before {ctx.invoked_subcommand} will not take effect")


if __name__ == "__main__":
    app()