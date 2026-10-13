#!/usr/bin/env bash
# Builds the pipeline status digest. Reads GitHub through `gh api` only.
# Writes outputs `post` (true|false) and `text` to $GITHUB_OUTPUT.
# Env: REPO, GH_TOKEN, FORCE (true|false), HEARTBEAT_SECONDS (default 21600),
#      DRY_RUN (true: print instead of writing outputs), GITHUB_RUN_ID.
set -euo pipefail

REPO=${REPO:-MoermansJ/hey-laika}
FORCE=${FORCE:-false}
HEARTBEAT=${HEARTBEAT_SECONDS:-21600}
NOW=$(date -u +%s)
OUT=${GITHUB_OUTPUT:-/dev/stdout}
W=$(mktemp -d)
ago() { local s=$(( NOW - $(date -u -d "$1" +%s) )); if [ $s -lt 3600 ]; then echo "$((s/60))m"; elif [ $s -lt 172800 ]; then echo "$((s/3600))h"; else echo "$((s/86400))d"; fi; }
age_s() { echo $(( NOW - $(date -u -d "$1" +%s) )); }

# ---- 1. previous digest (state is kept in `digest-state` job annotations) ----
PREV_FP=""; PREV_AT=0
for RID in $(gh api "repos/$REPO/actions/workflows/agent-digest.yml/runs?status=completed&per_page=15" --jq '.workflow_runs[].id' 2>/dev/null || true); do
  [ "$RID" = "${GITHUB_RUN_ID:-0}" ] && continue
  JID=$(gh api "repos/$REPO/actions/runs/$RID/jobs" --jq '.jobs[0].id' 2>/dev/null || true)
  [ -z "$JID" ] && continue
  ST=$(gh api "repos/$REPO/check-runs/$JID/annotations" --jq '[.[]|select(.title=="digest-state")|.message][0] // empty' 2>/dev/null || true)
  if [ -n "$ST" ] && echo "$ST" | grep -q 'posted=1'; then
    PREV_FP=$(echo "$ST" | sed -n 's/.*fp=\([0-9a-f]*\).*/\1/p'); PREV_AT=$(echo "$ST" | sed -n 's/.*at=\([0-9]*\).*/\1/p'); break
  fi
done
SINCE=$PREV_AT; [ $SINCE -lt $(( NOW - 86400 )) ] && SINCE=$(( NOW - 86400 ))
SINCE=${SINCE_OVERRIDE:-$SINCE}
SINCE_ISO=$(date -u -d "@$SINCE" +%Y-%m-%dT%H:%M:%SZ)

# ---- 2. tickets by status (excludes PRs) ----
: > "$W/issues.jsonl"
for S in to-do in-progress in-review blocked done; do
  # Only open tickets count as to-do/in-progress/in-review/blocked (a closed
  # ticket with a stale label is not work); AGENT-00 self-tests are ignored.
  STATE=open; [ "$S" = done ] && STATE=all
  gh api --paginate "repos/$REPO/issues?labels=status:$S&state=$STATE&per_page=100" \
    --jq ".[] | select(.pull_request==null and ([.labels[].name]|index(\"AGENT-00\")|not)) | {number,title,state,updated_at,status:\"$S\",labels:[.labels[].name]}" >> "$W/issues.jsonl"
done
jq -s '.' "$W/issues.jsonl" > "$W/issues.json"
cnt() { jq --arg s "$1" '[.[]|select(.status==$s)]|length' "$W/issues.json"; }
C_TODO=$(cnt to-do); C_PROG=$(cnt in-progress); C_REV=$(cnt in-review); C_BLK=$(cnt blocked); C_DONE=$(cnt done)

# needs-jon (open tickets carrying the label)
NEEDS=$(gh api "repos/$REPO/issues?labels=needs-jon&state=open&per_page=100" --jq '.[]|select(.pull_request==null)|"#\(.number) \(.title[0:50])"' | paste -sd';' - | sed 's/;/; /g')
N_NEEDS=$(gh api "repos/$REPO/issues?labels=needs-jon&state=open&per_page=100" --jq '[.[]|select(.pull_request==null)]|length')

# non-AGENT tickets sitting in progress (e.g. #50): listed, never ignored
NONAGENT=$(jq -r '.[]|select(.status=="in-progress" and ([.labels[]|select(test("^AGENT-[0-9]+$"))]|length==0))|"#\(.number) \(.title[0:40]) (since \(.updated_at))"' "$W/issues.json" | while IFS= read -r l; do d=$(echo "$l" | sed -n 's/.*(since \(.*\))/\1/p'); echo "$(echo "$l" | sed 's/ (since .*//') ($(ago "$d"))"; done | paste -sd';' - | sed 's/;/; /g')
# AGENT tickets in progress longer than 3h
STUCK_PROG=$(jq -r --argjson now "$NOW" '[.[]|select(.status=="in-progress" and ([.labels[]|select(test("^AGENT-[0-9]+$"))]|length>0) and ($now - (.updated_at|fromdateiso8601) > 10800))]|length' "$W/issues.json")
AGENT_PROG=$(jq '[.[]|select(.status=="in-progress" and ([.labels[]|select(test("^AGENT-[0-9]+$"))]|length>0))]|length' "$W/issues.json")

# ---- 3. PRs into development: created in the period, plus every open one ----
gh api "repos/$REPO/pulls?state=all&base=development&sort=created&direction=desc&per_page=100" \
  --jq '.[]|{number,title,state,merged:(.merged_at!=null),created_at,body:(.body//"")}' > "$W/prs.jsonl"
: > "$W/prrec.jsonl"
while IFS= read -r PR; do
  [ -z "$PR" ] && continue
  N=$(echo "$PR" | jq -r .number); ST=$(echo "$PR" | jq -r .state); CR=$(echo "$PR" | jq -r .created_at)
  IN_WINDOW=$([ $(date -u -d "$CR" +%s) -ge $SINCE ] && echo 1 || echo 0)
  [ "$ST" != "open" ] && [ "$IN_WINDOW" = 0 ] && continue
  VERDICT=$(gh api "repos/$REPO/issues/$N/comments?per_page=100" --jq '[.[]|select(.body|contains("<!-- agent-review -->"))|.body|capture("verdict=(?<v>PASS|FAIL)").v]|last // "none"')
  TNUM=$(echo "$PR" | jq -r '(.body|capture("(?i)implements #(?<n>[0-9]+)").n) // empty' 2>/dev/null || true)
  if [ -z "$TNUM" ]; then
    A=$(echo "$PR" | jq -r '.title|capture("(?<a>AGENT-[0-9]+)").a // empty' 2>/dev/null || true)
    [ -n "$A" ] && TNUM=$(jq -r --arg a "$A" '[.[]|select(.labels|index($a))][0].number // empty' "$W/issues.json")
  fi
  FAILS=0
  if [ -n "$TNUM" ]; then
    FAILS=$(gh api "repos/$REPO/issues/$TNUM" --jq '[.labels[].name|select(startswith("review-failed:"))|split(":")[1]|tonumber]|max // 0')
  fi
  echo "$PR" | jq -c --arg v "$VERDICT" --argjson f "${FAILS:-0}" --argjson w "$IN_WINDOW" '{number,title,state,merged,verdict:$v,fails:$f,inwindow:$w}' >> "$W/prrec.jsonl"
done < "$W/prs.jsonl"
jq -s '.' "$W/prrec.jsonl" > "$W/prrec.json"
fmt() { jq -r "$1" "$W/prrec.json" | paste -sd';' - | sed 's/;/; /g'; }
CREATED=$(fmt '.[]|select(.inwindow==1 and (.title|test("AGENT-00")|not))|"#\(.number) \(.title[0:45]) [\(if .merged then "merged" elif .state=="open" then "open" else "closed" end)]"')
[ ${#CREATED} -gt 600 ] && CREATED="${CREATED:0:600}…"
PASSED=$(fmt '.[]|select(.verdict=="PASS" and (.inwindow==1 or .state=="open"))|"#\(.number)"')
FAILED=$(fmt '.[]|select(.verdict=="FAIL" and .state=="open")|"#\(.number) \(.title[0:40]) (failed x\(.fails))"')
AWAIT=$(fmt '.[]|select(.verdict=="none" and .state=="open")|"#\(.number)"')
N_FAILED_OPEN=$(jq '[.[]|select(.verdict=="FAIL" and .state=="open")]|length' "$W/prrec.json")

# ---- 4. factory lock (#31) ----
LOCK=$(gh api "repos/$REPO/issues/31" --jq '{u:.updated_at,l:[.labels[].name]}')
LOCK_UPD=$(echo "$LOCK" | jq -r .u)
LOCK_STATE=$(echo "$LOCK" | jq -r '.l|map(select(startswith("factory:")))|first // "factory:unknown"')
LOCK_AGE=$(age_s "$LOCK_UPD")
STALE="no"
if [ "$LOCK_STATE" = "factory:running" ] && [ $LOCK_AGE -gt 2700 ]; then STALE="YES (running, no heartbeat for $(ago "$LOCK_UPD"); lock expired at 45m)"; fi
if [ "$LOCK_STATE" = "factory:idle" ] && [ $LOCK_AGE -gt 9000 ]; then STALE="YES (last factory activity $(ago "$LOCK_UPD") ago; hourly run missed)"; fi

# ---- 5. overall state ----
if [ "$N_NEEDS" -gt 0 ]; then OVERALL="NEEDS JON"
elif [ "${STALE:0:3}" = "YES" ] || [ "$C_BLK" -gt 0 ] || [ "$STUCK_PROG" -gt 0 ]; then OVERALL="STUCK"
elif [ "$LOCK_STATE" = "factory:running" ] || [ "$AGENT_PROG" -gt 0 ] || [ "$C_REV" -gt 0 ] || [ "$N_FAILED_OPEN" -gt 0 ]; then OVERALL="WORKING"
else OVERALL="IDLE"; fi
case "$OVERALL" in "NEEDS JON") I="🙋";; STUCK) I="🧱";; WORKING) I="🛠️";; *) I="💤";; esac

# ---- 6. message + fingerprint (fingerprint excludes anything time-based) ----
MSG="$I **Pipeline digest — $OVERALL**  (since $SINCE_ISO)
📦 PRs created: ${CREATED:-none}
✅ Passed review: ${PASSED:-none}
🔁 Needs more work: ${FAILED:-none}$( [ -n "$AWAIT" ] && echo "  | awaiting review: $AWAIT" )
📊 to-do $C_TODO · in-progress $C_PROG · in-review $C_REV · blocked $C_BLK · done $C_DONE
🙋 needs-jon: ${NEEDS:-none}
🧩 non-AGENT in progress: ${NONAGENT:-none}
🔒 factory $LOCK_STATE (#31 updated $(ago "$LOCK_UPD") ago) · stale: $STALE"
FP=$(printf '%s' "$OVERALL|$C_TODO|$C_PROG|$C_REV|$C_BLK|$C_DONE|$CREATED|$PASSED|$FAILED|$AWAIT|$NEEDS|$NONAGENT|$LOCK_STATE|${STALE:0:3}" | sha1sum | cut -c1-12)

POST=false; WHY="unchanged since last digest"
if [ "$FORCE" = "true" ]; then POST=true; WHY="forced"
elif [ -z "$PREV_FP" ]; then POST=true; WHY="no previous digest"
elif [ "$FP" != "$PREV_FP" ]; then POST=true; WHY="state changed"
elif [ $(( NOW - PREV_AT )) -ge "$HEARTBEAT" ]; then POST=true; WHY="heartbeat (>= $((HEARTBEAT/3600))h since last post)"; MSG="$MSG
_heartbeat: nothing changed in $(( (NOW-PREV_AT)/3600 ))h_"
fi
echo "digest decision: post=$POST ($WHY) fp=$FP prev_fp=${PREV_FP:-none}" >&2
if [ "$POST" = true ]; then PF=1; else PF=0; fi
echo "::notice title=digest-state::fp=$FP posted=$PF at=$NOW why=$WHY"
{
  echo "post=$POST"
  echo "text<<EOF_DIGEST"
  printf '%s\n' "$MSG"
  echo "EOF_DIGEST"
} >> "$OUT"
rm -rf "$W"
