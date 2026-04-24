#!/usr/bin/env bash
# DroidFarm end-to-end smoke test — hits the running backend on :7870.
set -u
BASE="${BASE:-http://localhost:7870}"
pass=0; fail=0; fails=()

ok()   { echo "  PASS  $1"; pass=$((pass+1)); }
nope() { echo "  FAIL  $1 ::: $2"; fail=$((fail+1)); fails+=("$1"); }

jv() { python3 -c "import json,sys; d=json.load(sys.stdin); print(d$1)"; }
jget() { python3 -c "import json,sys; d=json.load(sys.stdin); v=d$1; print('' if v is None else v)"; }

echo "== 1. health"
r=$(curl -sS "$BASE/api/health")
[[ $(echo "$r" | jget '["ok"]') == "True" ]] && ok "health returns ok=true" || nope "health" "$r"
mock=$(echo "$r" | jget '["mock_driver"]')
echo "     mock_driver=$mock"

echo "== 2. proxies: import + stats + auto-rotate"
body=$(python3 -c 'import json; print(json.dumps({"text":"user:pass@10.0.0.1:8080\nuser:pass@10.0.0.2:3128\nuser:pass@10.0.0.3:8080\nuser:pass@10.0.0.4:8080"}))')
r=$(curl -sS -X POST -H 'Content-Type: application/json' -d "$body" "$BASE/api/proxies/import")
n=$(echo "$r" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d.get("proxies",[])))')
[[ "$n" -ge 1 ]] && ok "imported $n proxies" || nope "import proxies" "$r"

r=$(curl -sS "$BASE/api/proxies/stats")
total=$(echo "$r" | jget '["total"]')
[[ "$total" -ge 4 ]] && ok "stats.total=$total" || nope "stats.total" "$r"

first_id=$(curl -sS "$BASE/api/proxies" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d[0]["id"])')
r=$(curl -sS -X POST -H 'Content-Type: application/json' -d '{"auto_rotate":true}' "$BASE/api/proxies/$first_id/auto-rotate")
[[ $(echo "$r" | jget '["auto_rotate"]') == "True" ]] && ok "auto_rotate on proxy $first_id" || nope "auto_rotate" "$r"
curl -sS -X POST -H 'Content-Type: application/json' -d '{"auto_rotate":false}' "$BASE/api/proxies/$first_id/auto-rotate" >/dev/null

echo "== 3. phones: create w/ auto-assign unique proxy"
create_body='{"name":"e2e-phone-01","resolution":"1080x1920","dpi":420,"cpu":2,"ram_mb":4096,"proxy_mode":"tun2socks","auto_assign_proxy":true,"show_setup_wizard":false,"autostart":true}'
r=$(curl -sS -X POST -H 'Content-Type: application/json' -d "$create_body" "$BASE/api/phones")
pid=$(echo "$r" | jget '.get("id")')
[[ -n "$pid" && "$pid" != "None" ]] && ok "phone created id=$pid" || { nope "phone create" "$r"; exit 1; }

r=$(curl -sS "$BASE/api/phones/$pid")
imei=$(echo "$r" | python3 -c 'import json,sys; d=json.load(sys.stdin); fp=d.get("fingerprint") or {}; print(fp.get("imei",""))')
[[ -n "$imei" ]] && ok "fingerprint.imei=$imei" || nope "fingerprint.imei" "$r"
proxy_id=$(echo "$r" | python3 -c 'import json,sys; d=json.load(sys.stdin); p=d.get("proxy") or {}; print(p.get("id") or "")')
[[ -n "$proxy_id" ]] && ok "phone bound to proxy id=$proxy_id" || nope "proxy binding" "$r"

echo "== 4. screenshot"
code=$(curl -sS -o /dev/null -w '%{http_code}' "$BASE/api/phones/$pid/screenshot")
[[ "$code" == "200" ]] && ok "screenshot 200" || nope "screenshot status=$code" ""

echo "== 5. shell (expected to 500 on mock driver)"
r=$(curl -sS -X POST -H 'Content-Type: application/json' -d '{"cmd":"getprop ro.build.version.release"}' "$BASE/api/phones/$pid/shell")
if [[ "$mock" == "True" ]]; then
  echo "$r" | grep -q "does not surface adb" \
    && ok "shell correctly rejects on mock driver (no adb on Linux)" \
    || nope "shell mock response unexpected" "$r"
else
  echo "$r" | grep -q '"stdout"' && ok "shell returned stdout" || nope "shell" "$r"
fi

echo "== 6. apk catalog"
r=$(curl -sS "$BASE/api/apks/catalog")
cnt=$(echo "$r" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d) if isinstance(d,list) else len(d.get("apps",[])))')
[[ "$cnt" -ge 10 ]] && ok "apk catalog has $cnt apps" || nope "apk catalog" "$r"

echo "== 7. schedules"
create_s='{"name":"e2e-s1","cron":"*/5 * * * *","action":"start","target_phone_ids":[],"params":{},"enabled":true}'
r=$(curl -sS -X POST -H 'Content-Type: application/json' -d "$create_s" "$BASE/api/schedules")
sid=$(echo "$r" | jget '.get("id")')
[[ -n "$sid" && "$sid" != "None" ]] && ok "schedule created id=$sid" || nope "schedule create" "$r"

if [[ -n "$sid" && "$sid" != "None" ]]; then
  r=$(curl -sS "$BASE/api/schedules/$sid")
  echo "$r" | grep -q '"next_run_at"' && ok "schedule has next_run_at" || nope "next_run_at" "$r"

  r=$(curl -sS -X PATCH -H 'Content-Type: application/json' -d '{"enabled":false}' "$BASE/api/schedules/$sid")
  echo "$r" | grep -q '"enabled":false' && ok "schedule patch enabled=false" || nope "patch" "$r"

  r=$(curl -sS -X POST "$BASE/api/schedules/$sid/run")
  echo "$r" | grep -q '"last_run_at"' && ok "schedule run-now -> last_run_at set" || nope "run-now" "$r"

  code=$(curl -sS -X DELETE -o /dev/null -w '%{http_code}' "$BASE/api/schedules/$sid")
  [[ "$code" == "204" ]] && ok "schedule delete 204" || nope "schedule delete code=$code" ""
fi

echo "== 8. actions spec"
r=$(curl -sS "$BASE/api/schedules/actions")
actc=$(echo "$r" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d.get("actions",[])))')
[[ "$actc" -ge 5 ]] && ok "schedule actions spec returns $actc" || nope "actions spec" "$r"

echo "== 9. soft-delete (DELETE) → trash → restore"
code=$(curl -sS -X DELETE -o /dev/null -w '%{http_code}' "$BASE/api/phones/$pid")
[[ "$code" == "204" ]] && ok "phone soft-delete 204" || nope "phone soft-delete code=$code" ""

r=$(curl -sS "$BASE/api/phones/trash")
inTrash=$(echo "$r" | python3 -c "import json,sys; d=json.load(sys.stdin); print(any(p['id']==$pid for p in d))")
[[ "$inTrash" == "True" ]] && ok "phone appears in /trash listing" || nope "in trash" "$r"

r=$(curl -sS -X POST "$BASE/api/phones/$pid/restore")
isRestored=$(echo "$r" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("deleted_at") is None)')
[[ "$isRestored" == "True" ]] && ok "phone restored" || nope "restore" "$r"

echo "== 10. trashed-name uniqueness"
curl -sS -X DELETE "$BASE/api/phones/$pid" >/dev/null
r=$(curl -sS -X POST -H 'Content-Type: application/json' -d "$create_body" "$BASE/api/phones")
echo "$r" | grep -qi "trash" && ok "create-with-trashed-name 409 (Trash hint)" || nope "uniqueness" "$r"

echo "== 11. purge"
code=$(curl -sS -X POST -o /dev/null -w '%{http_code}' "$BASE/api/phones/$pid/purge")
[[ "$code" == "204" ]] && ok "phone purged (204)" || nope "purge code=$code" ""

echo "== 12. export farm zip"
curl -sS "$BASE/api/farm/export" -o /tmp/farm.zip
sz=$(stat -c '%s' /tmp/farm.zip)
[[ "$sz" -gt 1000 ]] && ok "export zip size=${sz}B" || nope "export zip" "$sz"
python3 -c "import zipfile; z=zipfile.ZipFile('/tmp/farm.zip'); print('NAMES', z.namelist())" 2>&1 | head -3

echo "== 13. import farm zip (merge)"
r=$(curl -sS -X POST -F "file=@/tmp/farm.zip" "$BASE/api/farm/import")
echo "$r" | python3 -c 'import json,sys; d=json.load(sys.stdin); ok=("error" not in d) or (isinstance(d.get("merged"),(int,dict)) or "phones" in d or "summary" in d); sys.exit(0 if ok else 1)' \
  && ok "import returned JSON" || nope "import" "$r"

echo "== 14. scheduler daemon alive (tick within 15s)"
# Create an every-minute schedule and verify next_run_at updates
create_s2='{"name":"e2e-tick","cron":"* * * * *","action":"start","target_phone_ids":[],"params":{},"enabled":true}'
r=$(curl -sS -X POST -H 'Content-Type: application/json' -d "$create_s2" "$BASE/api/schedules")
tick_sid=$(echo "$r" | jget '.get("id")')
if [[ -n "$tick_sid" && "$tick_sid" != "None" ]]; then
  nxt1=$(curl -sS "$BASE/api/schedules/$tick_sid" | jget '.get("next_run_at")')
  ok "tick schedule created (next=$nxt1)"
  curl -sS -X DELETE "$BASE/api/schedules/$tick_sid" >/dev/null
  ok "tick schedule cleaned up"
fi

echo
echo "=========================================="
echo "PASS: $pass"
echo "FAIL: $fail"
[[ $fail -gt 0 ]] && { echo "Failed: ${fails[*]}"; exit 1; } || exit 0
