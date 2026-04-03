import csv
import sys
from collections import Counter

def main():
    if len(sys.argv) < 2:
        print("Usage: py make_demo_report.py <csv_path>")
        return

    path = sys.argv[1]
    total = 0
    crc_ok = 0
    cmd_cnt = Counter()
    t_vals = []
    h_vals = []
    d_vals = []
    i_vals = []

    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("source") != "frame":
                continue
            total += 1
            cmd = str(r.get("cmd", "")).strip()
            cmd_cnt[cmd] += 1
            if str(r.get("crc_ok", "")).strip() in ("1", "True", "true"):
                crc_ok += 1

            if r.get("temp_c"):
                t_vals.append(float(r["temp_c"]))
            if r.get("hum_rh"):
                h_vals.append(float(r["hum_rh"]))
            if r.get("dist_mm"):
                d_vals.append(float(r["dist_mm"]))
            if r.get("curr_ma"):
                i_vals.append(float(r["curr_ma"]))

    def mm(vals):
        if not vals:
            return ("-", "-", "-")
        return (f"{min(vals):.2f}", f"{sum(vals)/len(vals):.2f}", f"{max(vals):.2f}")

    t_min, t_avg, t_max = mm(t_vals)
    h_min, h_avg, h_max = mm(h_vals)
    d_min, d_avg, d_max = mm(d_vals)
    i_min, i_avg, i_max = mm(i_vals)

    print("=== Project A Demo Report ===")
    print(f"CSV: {path}")
    print(f"Total frame: {total}")
    print(f"CRC pass: {crc_ok}/{total}")
    if total == 0:
        print("WARN: no frame rows found (check UART link, COM port, or capture duration)")
    print(f"CMD count: {dict(cmd_cnt)}")
    print(f"A1 alarm count(cmd=161): {cmd_cnt.get('161', 0)}")
    print(f"A2 alarm count(cmd=162): {cmd_cnt.get('162', 0)}")
    print(f"Temp C min/avg/max: {t_min}/{t_avg}/{t_max}")
    print(f"RH % min/avg/max: {h_min}/{h_avg}/{h_max}")
    print(f"Dist mm min/avg/max: {d_min}/{d_avg}/{d_max}")
    print(f"Curr mA min/avg/max: {i_min}/{i_avg}/{i_max}")

if __name__ == "__main__":
    main()
