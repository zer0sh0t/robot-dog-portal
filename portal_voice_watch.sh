#!/bin/bash
# Watches heard.jsonl (Harin's mic->STT input) and injects each new line into the
# striker tmux session. Persists its processed-offset so restarts DON'T drop messages.
DIR="$(cd "$(dirname "$0")" && pwd)"
HEARD="$DIR/runtime/heard.jsonl"
OFFSET="$DIR/runtime/voice_watch.offset"
SESSION="striker"
inject(){ tmux has-session -t "$SESSION" 2>/dev/null || return 0
  tmux send-keys -t "$SESSION" -l "$1" 2>/dev/null; tmux send-keys -t "$SESSION" Enter 2>/dev/null; }
# init offset once (first-ever run = skip existing backlog; later runs resume from file)
if [ ! -f "$OFFSET" ]; then { wc -l < "$HEARD" 2>/dev/null || echo 0; } | tr -d ' ' > "$OFFSET"; fi
while true; do
  sleep 0.4
  [ -f "$HEARD" ] || continue
  last=$(cat "$OFFSET" 2>/dev/null || echo 0); now=$(wc -l < "$HEARD" 2>/dev/null || echo 0)
  if [ "$now" -gt "$last" ]; then
    while IFS= read -r line; do
      t=$(printf '%s' "$line" | python3 -c "import sys,json;print(json.loads(sys.stdin.read()).get('text',''))" 2>/dev/null)
      [ -n "$t" ] && inject "[portal voice] Harin said (reply in your voice via say.py, ONE short spoken sentence): $t"
    done < <(tail -n +"$((last+1))" "$HEARD")
    echo "$now" > "$OFFSET"
  fi
done

