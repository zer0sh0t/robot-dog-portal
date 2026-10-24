#!/usr/bin/env python3
"""say.py - striker speaks in a Piper voice (server-side neural TTS + ffmpeg processing).
Synthesizes text with Piper, applies a preset's deepen/character filter, writes
runtime/audio/<id>.wav, and appends {ts,text,id,audio} to runtime/say.jsonl.
The portal plays new audio ids.

Usage: python3 say.py "hey Harin, turning left now"
Preset via env VOICE_PRESET (A/B/C/D or blank for default)."""
import sys, os, json, time, subprocess

HERE = os.path.dirname(os.path.abspath(__file__)); RT = os.path.join(HERE,"runtime")
AUD  = os.path.join(RT,"audio"); os.makedirs(AUD, exist_ok=True)
SAY  = os.path.join(RT,"say.jsonl")
THINK= os.path.join(RT,"think.jsonl")
PY_BIN = os.path.expanduser("~/striker-piper-env/bin/python3")
VOICES = os.path.expanduser("~/piper-voices")
PRESET = os.environ.get("VOICE_PRESET","A").strip().upper()[:1]

# preset -> (voice, length_scale, ffmpeg filter). Deep/resonant/otherworldly.
PRESETS = {
    "":  ("en_US-ryan-high",    "1.12", "asetrate=22050*0.90,aresample=22050,atempo=1/0.90"),
    "A": ("en_US-norman-medium","1.15", "asetrate=22050*0.90,aresample=22050,atempo=1/0.90,aecho=0.8:0.85:55:0.30,lowpass=7500"),
    "B": ("en_US-ryan-high",    "1.16", "asetrate=22050*0.85,aresample=22050,atempo=1/0.85,chorus=0.5:0.9:50|55:0.4|0.3:0.30|0.35:2|1.5"),
    "C": ("en_GB-alan-medium",  "1.18", "asetrate=22050*0.83,aresample=22050,atempo=1/0.83,aphaser=type=t:speed=0.4:decay=0.3,aecho=0.8:0.8:45:0.25,lowpass=7000"),
    "D": ("en_US-norman-medium","1.20", "asetrate=22050*0.82,aresample=22050,atempo=1/0.82,acompressor=threshold=-18dB:ratio=4,chorus=0.6:0.9:55:0.4:0.3:2,aecho=0.8:0.85:70:0.35"),
}

def next_id():
    return sum(1 for _ in open(SAY)) if os.path.exists(SAY) else 0

def main():
    text = " ".join(sys.argv[1:]).strip()
    if not text: return
    i = next_id()
    raw = os.path.join(AUD, f"{i}_raw.wav"); out = os.path.join(AUD, f"{i}.wav")
    voice, length, filt = PRESETS.get(PRESET, PRESETS[""])
    audio_ok = False
    try:
        subprocess.run([PY_BIN,"-m","piper","-m",voice,"--data-dir",VOICES,
                        "--length-scale",length,"-f",raw],
                       input=text.encode(), check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
        subprocess.run(["ffmpeg","-y","-loglevel","error","-i",raw,"-af",filt,out],
                       check=True, timeout=30)
        if os.path.exists(raw): os.remove(raw)
        audio_ok = os.path.exists(out) and os.path.getsize(out) > 44
    except Exception as e:
        sys.stderr.write(f"piper synth failed ({e}); browser TTS fallback\n")
    open(SAY,"a").write(json.dumps({"ts":time.time(),"text":text,"id":i,"audio":audio_ok})+"\n")
    open(THINK,"a").write(json.dumps({"ts":time.time(),"kind":"striker","text":"\U0001F5E3 "+text})+"\n")
    print(f"speak[{i}] preset={PRESET or 'default'} audio={audio_ok}: {text}")

if __name__ == "__main__": main()
