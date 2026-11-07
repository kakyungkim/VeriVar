# CancerVar web-server calls (parsed)

`cancervar_predictions.json` holds the AMP/ASCO/CAP tier that the public CancerVar web server
(https://cancervar.wglab.org, WGLab) returned for each of the 70 Horak variants, parsed from the
server's result pages by `python -m scripts.fetch_cancervar`. Only the parsed tier labels are kept;
the raw HTML responses are not redistributed.

- **Source:** Li Q, Ren Z, Cao K, et al. CancerVar: an artificial intelligence-empowered platform for
  clinical interpretation of somatic mutations in cancer. *Sci Adv* 2022;8(18):eabj1624.
- **Terms:** the CancerVar README states that "CancerVar and OPAI is free for non-commercial use
  without warranty" and asks commercial users to contact the authors. This file is provided for
  non-commercial research reproduction only, under those terms.

CancerVar reports clinical-actionability tiers, not VICC oncogenicity, so the comparison in the
manuscript is cross-axis; see `scripts/run_cancervar_headtohead.py` and the manuscript caveat.
