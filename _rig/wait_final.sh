#!/bin/bash
for i in $(seq 1 50); do
  grep -q 'FINAL DONE' /root/gtb_test_results/order_test_final.log 2>/dev/null && break
  sleep 10
done
tail -150 /root/gtb_test_results/order_test_final.log
