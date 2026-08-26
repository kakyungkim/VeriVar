# Contributing to VeriVar

Thank you for your interest in contributing. VeriVar is research software for citation-grounded LLM interpretation of somatic variants, and contributions of all kinds are welcome — bug reports, documentation fixes, new tests, retrieval sources, and interpretation-arm improvements.

## Reporting issues

Please open a [GitHub issue](https://github.com/kakyungkim/VeriVar/issues) with:

- what you did (command or code), what you expected, and what happened;
- your OS and Python version;
- for interpretation-related issues, the variant (gene, HGVS) and the arm (generative / deterministic / rule / no-retrieval) involved.

Please do not include any private or patient-derived data in issues. VeriVar is built and evaluated on public data only.

## Development setup

```bash
git clone https://github.com/kakyungkim/VeriVar.git
cd VeriVar
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

## Running tests

The test suite runs offline and requires no API keys:

```bash
python -m pytest tests/ -q
```

All tests must pass before a pull request is reviewed. New features should come with tests; changes that touch the faithfulness contract (citation restriction, abstention) must include tests demonstrating the contract still holds.

## Pull requests

1. Fork the repository and create a feature branch.
2. Keep changes focused; separate unrelated changes into separate PRs.
3. Ensure `python -m pytest tests/ -q` passes.
4. Describe in the PR what changed and why, and note any effect on interpretation outputs.

## Scope guardrails

- VeriVar is **research and education software, not a clinical diagnostic device**. Contributions that present it as a clinical tool will not be accepted.
- Assertions in generated output must remain traceable to retrieved identifiers. Changes that weaken the faithfulness contract or the abstention rule require prior discussion in an issue.

## Questions

Open an issue, or contact the maintainer at kakyung.kim@gmail.com.
