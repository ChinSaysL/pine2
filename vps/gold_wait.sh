#!/bin/bash
# wait for the gold entry-filter experiment to finish, then snapshot the Phase B table
for i in $(seq 1 300); do
  grep -q 'gold filter experiment done' /root/gtb_test_results/gold_filters.log && break
  sleep 20
done
sed -n '/PHASE B/,$p' /root/gtb_test_results/gold_filters.log > /root/gtb_test_results/gold_final.txt
for v in base buf15 buf30 buf60 nyonly adx20 ema10 chan12; do
  f="/root/gtb_test_results/gold_B_$v.csv"
  if [ -f "$f" ]; then
    printf '%-7s ' "$v" >> /root/gtb_test_results/gold_final.txt
    awk -F';' 'NR>1 {n++; s+=$9; if($9>0){w+=$9; nn++} else l+=-$9} END {printf "trades %4d  total %+7.1fR  PF %.2f  win %.0f%%\n", n, s, (l>0?w/l:0), 100*nn/n}' "$f" \
      >> /root/gtb_test_results/gold_final.txt
  fi
done
echo "WAITER_DONE $(date -u '+%F %T')" >> /root/gtb_test_results/gold_final.txt
