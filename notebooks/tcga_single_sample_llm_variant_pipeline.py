# 🧬 LLM_Variant_Pipeline
# Copyright (c) 2026 Ka-Kyung Kim
# License: MIT
# GitHub: https://github.com/kakyungkim
#
# This notebook demonstrates LLM-assisted somatic variant interpretation
# for research/demo purposes only. Not intended for clinical use.

# 1️. 패키지 설치
# 기존 설치 제거 후, 지정 버전 설치
# !pip uninstall -y langchain langchain-core langchain-openai
!pip install -q \
  langchain-openai \
  pydantic \
  pandas

# 2. Library imports & environment check

# --- Standard library ---
import os
import sys
import glob
import gzip
import re
import tarfile
from io import BytesIO
from pathlib import Path
from getpass import getpass

# --- Third-party ---
import requests
import pandas as pd

import pydantic
from pydantic import BaseModel, Field
from typing import List, Optional

import langchain
import langchain_core
import langchain_openai
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

# Environment version logging (reproducibility)

import sys
from importlib.metadata import version, PackageNotFoundError

def get_pkg_version(pkg_name):
    try:
        return version(pkg_name)
    except PackageNotFoundError:
        return "not installed"

print("📦 Environment versions")
print("-----------------------")
print(f"Python           : {sys.version.split()[0]}")
print(f"langchain        : {get_pkg_version('langchain')}")
print(f"langchain-core   : {get_pkg_version('langchain-core')}")
print(f"langchain-openai : {get_pkg_version('langchain-openai')}")
print(f"pydantic         : {get_pkg_version('pydantic')}")
print(f"pandas           : {get_pkg_version('pandas')}")

# 3. API Key 설정 (Colab 숨김)
# ⚠️ 실제 노트북에서는 직접 입력 또는 Secret Manager 사용 권장
API_KEY = getpass("Enter your OpenAI API Key: ")  # <--- 사용자 입력
os.environ["OPENAI_API_KEY"] = API_KEY
print("✅ API Key set!")

# 4. Google Drive 마운트
from google.colab import drive
drive.mount('/content/drive')

# 5. 프로젝트 폴더 경로 설정
PROJECT_DIR = Path("/content/drive/MyDrive/ToyProjects/LLM_Variant_Pipeline")
BASE_DIR = PROJECT_DIR / "data"
OUTPUT_DIR = PROJECT_DIR / "reports"

BASE_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print(f"✅ Project directories ready!\nBASE_DIR: {BASE_DIR}\nOUTPUT_DIR: {OUTPUT_DIR}")


import requests
from pathlib import Path

OWNER = "ICGC-TCGA-PanCancer"
REPO = "vcf-uploader"
PATH = "sample_files"
BRANCH = "develop"

# GitHub API로 sample_files 목록 조회
api_url = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{PATH}?ref={BRANCH}"
resp = requests.get(api_url)
resp.raise_for_status()
files = resp.json()

# 파일명에 'somatic'이 포함된 항목 필터링
somatic_urls = [
    f["download_url"]
    for f in files
    if "somatic" in f["name"].lower()
]

print(f"Number of somatic-related files to download: {len(somatic_urls)}")
for u in somatic_urls:
    print(" -", u.split("/")[-1])

# 다운로드
for url in somatic_urls:
    fname = url.split("/")[-1]
    out_path = Path(BASE_DIR) / fname
    print(f"Downloading {fname}...")
    r = requests.get(url)
    r.raise_for_status()
    with open(out_path, "wb") as f:
        f.write(r.content)

print("Download complete at:", BASE_DIR)


sorted(p.name for p in BASE_DIR.iterdir())

vcf_files = list(BASE_DIR.glob("*.vcf.gz"))

snv_mnv_files = [f for f in vcf_files if "snv" in f.name.lower()]
indel_files   = [f for f in vcf_files if "indel" in f.name.lower()]

print("SNV/MNV files:")
for f in snv_mnv_files:
    print(" -", f.name)

print("\nINDEL files:")
for f in indel_files:
    print(" -", f.name)


import gzip
import pandas as pd

def parse_vcf_to_df(vcf_path, variant_type):
    rows = []

    with gzip.open(vcf_path, "rt") as f:
        for line in f:
            if line.startswith("#"):
                continue

            chrom, pos, _, ref, alt, _, _, info = line.strip().split("\t")[:8]

            rows.append({
                "chrom": chrom,
                "pos": int(pos),
                "ref": ref,
                "alt": alt,
                "variant_type": variant_type,
                "info": info
            })

    return pd.DataFrame(rows)


dfs = []

for f in snv_mnv_files:
    dfs.append(parse_vcf_to_df(f, "snv_mnv"))

for f in indel_files:
    dfs.append(parse_vcf_to_df(f, "indel"))

df_variants = pd.concat(dfs, ignore_index=True)
df_variants.head()


def extract_gene(info):
    match = re.search(r"SNPEFF_GENE_NAME=([^;]+)", info)
    return match.group(1) if match else None

df_variants["gene"] = df_variants["info"].apply(extract_gene)
df_variants.head()


MAX_VARIANTS = 10

df_candidates = (
    df_variants
    .sort_values(by=["gene"], na_position="last")
    .head(MAX_VARIANTS)
    .copy()
)

df_candidates

def variants_to_text(df):
    lines = []
    for _, r in df.iterrows():
        lines.append(
            f"{r.chrom}:{r.pos} {r.ref}>{r.alt} "
            f"[{r.variant_type}] "
            f"GENE={r.gene} INFO={r.info}"
        )
    return "\n".join(lines)

variant_text = variants_to_text(df_candidates)
print(variant_text)


from pydantic import BaseModel
from typing import List, Optional

class VariantInterpretation(BaseModel):
    gene: Optional[str]
    variant: str
    variant_type: str

    oncogenic_evidence: str
    potential_tier: str
    tier_basis: str

    requires_additional_validation: bool
    notes: Optional[str]


class SampleInterpretation(BaseModel):
    cancer_context: Optional[str]

    variants: List[VariantInterpretation]

    overall_summary: str
    limitations: str



# from langchain_openai import ChatOpenAI
# from langchain_core.output_parsers import JsonOutputParser

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
parser = JsonOutputParser(pydantic_object=SampleInterpretation)

# Mode 선택용 설정값
TIER_MODE = "llm"      # 또는 "rule"

from langchain_core.prompts import ChatPromptTemplate

def build_prompt_template(tier_mode: str) -> ChatPromptTemplate:
    if tier_mode == "llm":
        tier_instruction = """
You may assign a candidate tier based on available evidence.
Use conditional language only.
"""
    elif tier_mode == "rule":
        tier_instruction = """
Candidate tier has been pre-assigned using rule-based logic.
Do NOT change the tier. Only provide explanation.
"""
    else:
        raise ValueError("tier_mode must be 'llm' or 'rule'")

    return ChatPromptTemplate.from_template(f"""
You are interpreting somatic variants from a single tumor sample.

Constraints:
- Single-sample analysis only
- No cohort-level frequency data
- No definitive clinical decisions

{tier_instruction}

Variants:
{{variant_text}}

Cancer context:
{{cancer_context}}

Tier definitions:
- candidate_Tier_I: strong known oncogenic relevance
- candidate_Tier_II: moderate or emerging evidence
- uncertain: insufficient evidence

Output only valid JSON matching this schema:
{{format_instructions}}
""")

prompt_tmpl = build_prompt_template(TIER_MODE)

messages = prompt_tmpl.format_messages(
    variant_text=variant_text,
    cancer_context="pancreatic adenocarcinoma",
    format_instructions=parser.get_format_instructions()
)

# 1) 파이프라인 메타데이터
# NOTE:
# TCGA sample identifier is inferred from VCF filename.
# In multi-sample or production settings, explicit sample metadata should be used.
SAMPLE_ID = snv_mnv_files[0].stem

# 2) LLM 실행
result = llm.invoke(messages)
parsed = parser.parse(result.content)

# 3) LLM 결과 + sample_id 결합
final_result = {
    "sample_id": SAMPLE_ID,
    "cancer_context": "pancreatic adenocarcinoma",
    "variants": parsed["variants"],
    "overall_summary": parsed["overall_summary"],
    "limitations": parsed["limitations"]
}

# 공통 메타데이터
SAMPLE_ID = snv_mnv_files[0].stem
CANCER_CONTEXT = "pancreatic adenocarcinoma"

prompt_llm = build_prompt_template("llm")

messages_llm = prompt_llm.format_messages(
    variant_text=variant_text,
    cancer_context=CANCER_CONTEXT,
    format_instructions=parser.get_format_instructions()
)

result_llm = llm.invoke(messages_llm)
parsed_llm = parser.parse(result_llm.content)

# def assign_candidate_tier(row):
#     """
#     Demo-only rule-based pre-tiering.
#     Not intended for clinical or guideline-compliant use.
#     """
#     if row["gene"] in {"KRAS", "EGFR", "BRAF"}:
#         return "candidate_Tier_I"
#     elif row["gene"] is not None:
#         return "candidate_Tier_II"
#     else:
#         return "uncertain"

# df_candidates["rule_based_tier"] = df_candidates.apply(
#     assign_candidate_tier, axis=1
# )

# Minimal cancer-relevant gene set (demo)
KNOWN_ONCOGENES = {
    "KRAS", "NRAS", "HRAS",
    "EGFR", "BRAF", "PIK3CA",
    "TP53", "CDKN2A", "SMAD4"
}

def assign_candidate_tier(row):
    """
    Rule-based candidate tiering (INTENTIONALLY MINIMAL).

    Conceptual mapping to AMP/ASCO/CAP guidelines:
    - candidate_Tier_I   ~ AMP Tier I/II (strong clinical or biological evidence)
    - candidate_Tier_II  ~ AMP Tier III (biological relevance, limited evidence)
    - uncertain          ~ AMP Tier IV (unknown significance)

    This rule is NOT guideline-compliant and is used only
    to provide a stable comparison baseline for LLM behavior.
    """

    gene = row["gene"]

    # Well-established oncogenes / tumor suppressors
    if gene in KNOWN_ONCOGENES:
        return "candidate_Tier_I"

    # Missing or undefined gene
    if gene is None:
        return "uncertain"

    # Pseudogenes / uncharacterized loci (very coarse heuristic)
    if gene.endswith("L") or gene.startswith("LOC"):
        return "uncertain"

    # Fallback: gene-level relevance but no strong evidence
    return "candidate_Tier_II"


df_candidates = df_candidates.copy()
df_candidates["rule_based_tier"] = df_candidates.apply(
    assign_candidate_tier, axis=1
)

# (선택) sanity check
df_candidates[["gene", "rule_based_tier"]].head()

def variants_to_text_with_rule(df):
    lines = []
    for _, r in df.iterrows():
        lines.append(
            f"{r['chrom']}:{r['pos']} {r['ref']}>{r['alt']} "
            f"[{r['variant_type']}] "
            f"GENE={r['gene']} PRE_TIER={r['rule_based_tier']}"
        )
    return "\n".join(lines)

variant_text_rule = variants_to_text_with_rule(df_candidates)
print(variant_text_rule)


prompt_rule = build_prompt_template("rule")

messages_rule = prompt_rule.format_messages(
    variant_text=variant_text_rule,
    cancer_context=CANCER_CONTEXT,
    format_instructions=parser.get_format_instructions()
)

result_rule = llm.invoke(messages_rule)
parsed_rule = parser.parse(result_rule.content)

dual_mode_result = {
    "sample_id": SAMPLE_ID,
    "cancer_context": CANCER_CONTEXT,
    "llm_mode": parsed_llm,
    "rule_mode": parsed_rule
}

# --- 1) variant key 정의 함수 ---
def make_variant_key(v):
    return f"{v['variant']}|{v['variant_type']}"

# --- 2) LLM / Rule 결과를 dict로 변환 ---
llm_map = {
    make_variant_key(v): v
    for v in parsed_llm["variants"]
}

rule_map = {
    make_variant_key(v): v
    for v in parsed_rule["variants"]
}

# --- 3) 공통 key 기준으로 비교 ---
rows = []

for key in llm_map.keys() & rule_map.keys():
    v_llm = llm_map[key]
    v_rule = rule_map[key]

    rows.append({
        "gene": v_llm.get("gene"),
        "variant": v_llm["variant"],
        "variant_type": v_llm["variant_type"],
        "LLM_candidate_tier": v_llm["potential_tier"],
        "Rule_candidate_tier": v_rule["potential_tier"],
        "LLM_tier_basis": v_llm["tier_basis"],
        "Rule_tier_basis": v_rule["tier_basis"],
        "LLM_requires_validation": v_llm["requires_additional_validation"]
    })

comparison_df = pd.DataFrame(rows)
comparison_df["tier_match"] = (
    comparison_df["LLM_candidate_tier"]
    == comparison_df["Rule_candidate_tier"]
)

concordant_df = comparison_df.loc[comparison_df["tier_match"]]
concordant_df

discordant_df = comparison_df.loc[~comparison_df["tier_match"]]
discordant_df

comparison_df.to_csv(
    OUTPUT_DIR / f"{SAMPLE_ID}_dual_mode_comparison.csv",
    index=False
)
