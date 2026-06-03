"""Extract the Horak 2022 oncogenicity gold standard into a clean TSV.

Source: ClinGen/CGC/VICC (Horak et al., Genet Med 2022), Supplemental Table 3
(PMC9081216). 70 somatic variants in 9 genes with expert VICC oncogenicity
classifications + point totals + SOP codes. Used as an EXTERNAL benchmark.

Citation required; academic/non-commercial use. Build38 + build37 coordinates.

Run:  python -m scripts.build_horak_benchmark
Output: data/benchmark/horak_benchmark.tsv
"""
import sys
from pathlib import Path

import pandas as pd

SRC = Path("data/benchmark/horak/NIHMS1781706-supplement-3.xlsx")
OUT = Path("data/benchmark/horak_benchmark.tsv")


def main():
    if not SRC.exists():
        print(f"[!] {SRC} not found (download supplement-3.xlsx from PMC9081216).")
        return 1
    d = pd.read_excel(SRC, header=3)
    # Column positions (Supplemental table 3 layout):
    cols = {"gene": 0, "aa": 3,
            "b38_chr": 6, "b38_pos": 7, "b38_ref": 9, "b38_alt": 10,
            "b37_chr": 11, "b37_pos": 12, "b37_ref": 13, "b37_alt": 14,
            "oncogenicity": 15, "points": 16, "sop_codes": 17}
    rows = []
    for i in range(len(d)):
        gene = str(d.iloc[i, cols["gene"]]).strip()
        onc = str(d.iloc[i, cols["oncogenicity"]]).strip()
        if gene in ("nan", "") or onc in ("nan", ""):
            continue
        rec = {k: (str(d.iloc[i, c]).strip() if not isinstance(d.iloc[i, c], float) or pd.notna(d.iloc[i, c]) else "")
               for k, c in cols.items()}
        rec["gene"] = gene
        rec["oncogenicity"] = onc
        rows.append(rec)

    out = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, sep="\t", index=False)
    print(f"[+] {len(out)} Horak variants -> {OUT}")
    print("    classes:", out["oncogenicity"].value_counts().to_dict())
    return 0


if __name__ == "__main__":
    sys.exit(main())
