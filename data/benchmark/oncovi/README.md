# OncoVI example predictions

`SOP_table_union_OncoVI_prediction.xlsx` is OncoVI's own published output for the variants of the
ClinGen/CGC/VICC SOP table, copied unchanged from the OncoVI repository
(`exampleoutput/SOP_table_union_OncoVI_prediction.xlsx` at https://github.com/MGCarta/oncovi).
It is the comparator file for `python -m scripts.run_oncovi_headtohead`, which writes
`data/benchmark/oncovi_headtohead.json`.

- **Source:** Carta MG, Tögel L, Hölsken A, et al. Oncogenicity Variant Interpreter (OncoVI). *J Mol Diagn* 2026;28(6):469-484,
  doi:10.1016/j.jmoldx.2026.03.004; code at https://github.com/MGCarta/oncovi.
- **License:** MIT. The copyright notice and permission notice are reproduced in `LICENSE` in this
  folder, as the MIT license requires.

Two other files that ship with the OncoVI repository are deliberately **not** redistributed here:
`oncogenes_cgc.csv` and `tsg_cgc.csv` are COSMIC Cancer Gene Census extracts, which the COSMIC
licence does not allow to be redistributed, and no code in this repository reads them.
