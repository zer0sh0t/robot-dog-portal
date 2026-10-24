#!/usr/bin/env python3
"""think.py - striker narrates to the portal. Appends a line to runtime/think.jsonl.
Usage: python3 think.py "reasoning text"           (a thought)
       python3 think.py --cmd "walk fwd x=15"       (a command sent)
       python3 think.py --info "note"
"""
import sys, os, json, time
RT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"runtime"); os.makedirs(RT,exist_ok=True)
kind="think"; args=sys.argv[1:]
if args and args[0] in ("--cmd","--info","--think"): kind=args.pop(0)[2:]
text=" ".join(args)
open(os.path.join(RT,"think.jsonl"),"a").write(json.dumps({"ts":time.time(),"kind":kind,"text":text})+"\n")
print("logged:",kind,text)
