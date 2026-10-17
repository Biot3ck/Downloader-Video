"""Run actual DNS -> Broker -> numeric socket within network=none."""
from pathlib import Path
import sys
from run_numeric_wire import main

if __name__ == '__main__':
    main(probe=(Path(__file__).with_name('integrated_probe.py')).read_text(),
         extra_files=('clipora_v8_firewall_candidate/dns_snapshot.py',),
         report_path=sys.argv[1] if len(sys.argv)>1 else None)
