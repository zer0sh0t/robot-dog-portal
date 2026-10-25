#!/usr/bin/env python3
"""Striker robot-dog mission-control portal (v1).

Serves a live dashboard over Tailscale: striker's thinking feed + command log,
camera, telemetry (battery/connection), and a big E-STOP.

- Bind to the Tailscale IP only (default) so it's private to the tailnet.
- striker narrates by appending JSON lines to runtime/think.jsonl (use think.py).
- E-STOP: POST /estop -> sets runtime/estop.flag AND (if robot reachable) SSHes a
  zero-velocity publish to /puppy_control/velocity. Stopping is always safe/allowed.

Run:  python3 server.py            (binds tailscale ip :8088)
      PORTAL_BIND=0.0.0.0 python3 server.py   (all ifaces - avoid; tailnet-only is safer)
"""
import http.server, socketserver, json, os, subprocess, threading, time, urllib.request, urllib.parse, ssl
import shlex
from sensor_state import SensorState
from reasoning import from_sensors

HERE = os.path.dirname(os.path.abspath(__file__))
RT   = os.path.join(HERE, "runtime")
THINK = os.path.join(RT, "think.jsonl")
ESTOP = os.path.join(RT, "estop.flag")
TELEM = os.path.join(RT, "telemetry.json")
SAY   = os.path.join(RT, "say.jsonl")     # things striker wants the phone to SPEAK
HEARD = os.path.join(RT, "heard.jsonl")   # things Harin said (mic -> STT)
ROBOT = os.environ.get("PUPPY_HOST", "100.82.148.107")
BIND  = os.environ.get("PORTAL_BIND", "100.69.20.22")   # LattePanda tailnet IP
PORT  = int(os.environ.get("PORTAL_PORT", "8088"))
CAM_TOPIC = os.environ.get("PUPPY_CAM_TOPIC", "/usb_cam_striker/image_raw")
# LOCAL=1 when the portal runs ON the dog itself: run commands locally (no ssh-to-self)
LOCAL = os.environ.get("PUPPY_LOCAL") == "1"
SENSORS = SensorState(float(os.environ.get("PORTAL_SENSOR_STALE_SECONDS", "10")),
                      os.environ.get("PUPPY_SMOKE_UNIT", "raw"))


def watch_fire_sensors():
    """Stream ROS subscriber callbacks through the existing local/SSH Docker bridge."""
    config = {
        "smoke": [os.environ.get("PUPPY_SMOKE_TOPIC", "/smoke"), "std_msgs/Float32"],
        "temperature": [os.environ.get("PUPPY_TEMPERATURE_TOPIC", "/temperature"),
                        os.environ.get("PUPPY_TEMPERATURE_TYPE", "sensor_msgs/Temperature")],
        "smoke_detected": [os.environ.get("PUPPY_SMOKE_DETECTED_TOPIC", "/smoke_detected"), "std_msgs/Bool"],
        "camera": [os.environ.get("PUPPY_CAMERA_ALERT_TOPIC", "/camera_fire_detected"), "std_msgs/Bool"],
        "fire_sensor_fault": [os.environ.get("PUPPY_SENSOR_FAULT_TOPIC", "/fire_sensor_fault"), "std_msgs/Bool"],
        "fire_alert": [os.environ.get("PUPPY_FIRE_ALERT_TOPIC", "/fire_alert"), "std_msgs/Bool"],
    }
    if config["temperature"][1] not in ("sensor_msgs/Temperature", "std_msgs/Float32"):
        raise ValueError("PUPPY_TEMPERATURE_TYPE must be sensor_msgs/Temperature or std_msgs/Float32")
    with open(os.path.join(HERE, "fire_sensors.py")) as f:
        script = f.read()
    inner = ('source /opt/ros/noetic/setup.bash; '
             'source /home/ubuntu/puppypi/devel/setup.bash 2>/dev/null; '
             'export ROS_MASTER_URI=http://localhost:11311; exec python3 -u -c '
             + shlex.quote(script) + ' ' + shlex.quote(json.dumps(config)))
    command = 'docker exec ' + shlex.quote(os.environ.get("PUPPY_ROS_CONTAINER", "puppypi")) + ' bash -lc ' + shlex.quote(inner)
    args = (["bash", "-lc", command] if LOCAL else
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
             "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=2",
             f"pi@{ROBOT}", command])
    while True:
        process = None
        try:
            process = subprocess.Popen(args, stdout=subprocess.PIPE, text=True)
            for line in process.stdout:
                try:
                    message = json.loads(line)
                    SENSORS.update(message["sensor"], message["value"])
                except (ValueError, KeyError, TypeError):
                    continue
        except OSError as exc:
            print(f"sensor bridge: {exc}", flush=True)
        finally:
            SENSORS.disconnect()
            if process is not None:
                process.stdout.close()
                process.wait()
        time.sleep(3)

os.makedirs(RT, exist_ok=True)

def ssh(cmd, timeout=12):
    if LOCAL:
        return subprocess.run(["bash","-lc",cmd], capture_output=True, text=True, timeout=timeout+5)
    return subprocess.run(["ssh","-o","BatchMode=yes","-o",f"ConnectTimeout={timeout}",
        f"pi@{ROBOT}", cmd], capture_output=True, text=True, timeout=timeout+5)

def robot_online():
    if LOCAL:
        return True
    try:
        r = subprocess.run(["ping","-c","1","-W","2",ROBOT], capture_output=True)
        return r.returncode == 0
    except Exception:
        return False

def poll_telemetry():
    while True:
        t = {"ts": time.time(), "online": False, "battery_v": None, "note": ""}
        try:
            if robot_online():
                t["online"] = True
                r = ssh('docker exec puppypi bash -lc "source /opt/ros/noetic/setup.bash; '
                        'source /home/ubuntu/puppypi/devel/setup.bash 2>/dev/null; '
                        'export ROS_MASTER_URI=http://localhost:11311; '
                        'timeout 6 rostopic echo -n1 /ros_robot_controller/battery 2>/dev/null | grep -oE \\"[0-9]+\\" | head -1"')
                mv = r.stdout.strip()
                if mv.isdigit():
                    t["battery_v"] = round(int(mv)/1000.0, 2)
            else:
                t["note"] = "robot offline"
        except Exception as e:
            t["note"] = f"poll error: {e}"
        try:
            json.dump(t, open(TELEM,"w"))
        except Exception:
            pass
        time.sleep(4)

def estop_fire():
    open(ESTOP,"w").write(str(time.time()))
    # append a thought
    with open(THINK,"a") as f:
        f.write(json.dumps({"ts":time.time(),"kind":"ESTOP","text":"E-STOP pressed - halting: publishing zero velocity."})+"\n")
    # if reachable, publish zero velocity a few times (stop is always safe)
    if robot_online():
        try:
            ssh('docker exec puppypi bash -lc "mkdir -p /home/ubuntu/striker_control; touch /home/ubuntu/striker_control/ESTOP.flag; source /opt/ros/noetic/setup.bash; '
                'source /home/ubuntu/puppypi/devel/setup.bash 2>/dev/null; '
                'export ROS_MASTER_URI=http://localhost:11311; '
                'for i in 1 2 3; do rostopic pub -1 /puppy_control/velocity puppy_control/Velocity \\"{x: 0.0, y: 0.0, yaw_rate: 0.0}\\" 2>/dev/null; done"', timeout=15)
        except Exception:
            pass

def tail_jsonl(path, n=120):
    if not os.path.exists(path): return []
    try:
        lines = open(path).read().strip().split("\n")[-n:]
        return [json.loads(l) for l in lines if l.strip()]
    except Exception:
        return []

INDEX = open(os.path.join(HERE,"index.html")).read() if os.path.exists(os.path.join(HERE,"index.html")) else "<h1>portal</h1>"

class H(http.server.BaseHTTPRequestHandler):
    timeout = 15
    def log_message(self, *a): pass
    def handle_one_request(self):
        try: return super().handle_one_request()
        except Exception: 
            try: self.close_connection = True
            except Exception: pass
    def _send(self, code, ctype, body):
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control","no-store"); self.end_headers()
        if isinstance(body,str): body=body.encode()
        self.wfile.write(body)
    def do_GET(self):
        p = urllib.parse.urlparse(self.path).path
        if p in ("/","/index.html"):
            self._send(200,"text/html", open(os.path.join(HERE,"index.html")).read()); return
        if p == "/state.json":
            telem = json.load(open(TELEM)) if os.path.exists(TELEM) else {}
            say=[{"id":m.get("id",i),"text":m.get("text",""),"audio":m.get("audio",False)} for i,m in enumerate(tail_jsonl(SAY, 80))]
            sensors = SENSORS.snapshot()
            st = {"ts":time.time(),"estop":os.path.exists(ESTOP),
                  "telemetry":telem,"sensors":sensors,"hazard":from_sensors(sensors),"feed":tail_jsonl(THINK),"say":say}
            self._send(200,"application/json", json.dumps(st)); return
        if p == "/camstream":
            try:
                url=f"http://{ROBOT}:8080/stream?topic={urllib.parse.quote(CAM_TOPIC)}&quality=25"
                up=urllib.request.urlopen(url, timeout=8)
                self.send_response(200)
                self.send_header("Content-Type", up.headers.get("Content-Type","multipart/x-mixed-replace;boundary=boundarydonotcross"))
                self.send_header("Cache-Control","no-store"); self.end_headers()
                while True:
                    chunk=up.read(8192)
                    if not chunk: break
                    self.wfile.write(chunk)
            except Exception:
                pass
            return
        if p == "/camera.jpg":
            try:
                url=f"http://{ROBOT}:8080/snapshot?topic={urllib.parse.quote(CAM_TOPIC)}"
                data=urllib.request.urlopen(url,timeout=6).read()
                self._send(200,"image/jpeg",data); return
            except Exception:
                self._send(503,"text/plain","camera offline"); return
        if p.startswith("/audio/"):
            frag=p.split("/audio/",1)[1]
            try: aid=str(int(frag.split(".")[0]))
            except Exception: self._send(404,"text/plain","bad id"); return
            wav=os.path.join(RT,"audio",aid+".wav")
            if os.path.exists(wav):
                self._send(200,"audio/wav", open(wav,"rb").read()); return
            self._send(404,"text/plain","no audio"); return
        self._send(404,"text/plain","not found")
    def do_POST(self):
        p = urllib.parse.urlparse(self.path).path
        if p == "/estop":
            threading.Thread(target=estop_fire,daemon=True).start()
            self._send(200,"application/json", json.dumps({"ok":True,"estop":True})); return
        if p == "/speak_test":
            q=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            preset=(q.get("preset",[""])[0] or "").upper()[:1]
            line="Good friend. This is my voice now. Striker, standing by, ready to move."
            env=dict(os.environ); 
            if preset: env["VOICE_PRESET"]=preset
            try:
                subprocess.run(["python3", os.path.join(HERE,"say.py"), line], cwd=HERE, timeout=90,
                               env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception: pass
            items=tail_jsonl(SAY,1); aid=items[-1].get("id") if items else None
            self._send(200,"application/json", json.dumps({"ok":True,"id":aid})); return
        if p == "/heard":
            ln=int(self.headers.get("Content-Length","0") or 0)
            body=self.rfile.read(ln).decode("utf-8","ignore") if ln else ""
            try: text=json.loads(body).get("text","").strip()
            except Exception: text=body.strip()
            if text:
                rec={"ts":time.time(),"text":text}
                open(HEARD,"a").write(json.dumps(rec)+"\n")
                with open(THINK,"a") as f:
                    f.write(json.dumps({"ts":time.time(),"kind":"harin","text":"\U0001F399 "+text})+"\n")
            self._send(200,"application/json", json.dumps({"ok":True})); return
        if p == "/estop/clear":
            if os.path.exists(ESTOP): os.remove(ESTOP)
            try:
                if robot_online(): ssh('docker exec puppypi rm -f /home/ubuntu/striker_control/ESTOP.flag', timeout=12)
            except Exception: pass
            with open(THINK,"a") as f:
                f.write(json.dumps({"ts":time.time(),"kind":"info","text":"E-STOP cleared."})+"\n")
            self._send(200,"application/json", json.dumps({"ok":True,"estop":False})); return
        self._send(404,"text/plain","not found")

if __name__ == "__main__":
    threading.Thread(target=watch_fire_sensors, daemon=True).start()
    threading.Thread(target=poll_telemetry, daemon=True).start()
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    socketserver.ThreadingTCPServer.daemon_threads = True
    httpd = socketserver.ThreadingTCPServer((BIND,PORT), H)
    cert=os.environ.get("PORTAL_CERT"); key=os.environ.get("PORTAL_KEY")
    scheme="http"
    if cert and key and os.path.exists(cert) and os.path.exists(key):
        ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain(cert,key)
        httpd.socket=ctx.wrap_socket(httpd.socket, server_side=True); scheme="https"
    print(f"portal on {scheme}://{BIND}:{PORT}")
    httpd.serve_forever()

