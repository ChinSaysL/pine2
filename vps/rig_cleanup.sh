#!/bin/bash
# Removes the isolated execution-test rig (the private Wine prefix copy + the two portable
# MT5 TEST installs). Leaves /root/gtb_test_results (the evidence) alone and never touches
# /home/mt5/.wine.
set -uo pipefail
TST_PREFIX=/home/mt5/.wine-test
echo "=== killing any rig wine processes"
sudo -u mt5 -H env WINEPREFIX="$TST_PREFIX" wineserver -k 2>/dev/null
sleep 2
pgrep -u mt5 -af "MetaTrader 5 TEST" | cut -c1-120
echo "=== removing $TST_PREFIX"
rm -rf "$TST_PREFIX"
rm -f /home/mt5/gtb/rig_run_gold.sh /home/mt5/gtb/rig_run_nq.sh
echo "=== disk"; df -h / | tail -1
echo "=== evidence kept"; ls -la /root/gtb_test_results
echo "=== live services"; systemctl is-active gtb-mt5 gtb-mt5-nq gtb-xvfb gtb-vnc gtb-notifier
