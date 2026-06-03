import pandas as pd
from pathlib import Path
from typing import Optional, Union


def _classify_variant_type(ref: str, alt: str) -> str:
    """Classify a single ref/alt pair as 'SNV' or 'INDEL'.

    A substitution of equal-length ref and alt (typically 1bp) is an SNV;
    anything that changes sequence length is treated as an INDEL.
    """
    if len(ref) == 1 and len(alt) == 1:
        return "SNV"
    if len(ref) == len(alt):
        # Multi-nucleotide substitution (MNV) — grouped with SNV for tiering.
        return "SNV"
    return "INDEL"


def _parse_first_float(value: str) -> Optional[float]:
    """Parse a (possibly multi-allelic, comma-separated) numeric field.

    VCF FORMAT fields such as AF are ``Number=A`` (one value per ALT allele).
    The parser splits one record per ALT allele upstream, so we take the
    matching (here: first) value rather than calling ``float()`` on the whole
    comma-joined string, which would silently fail and drop the value.
    """
    if value is None:
        return None
    token = value.split(",")[0].strip()
    try:
        return float(token)
    except ValueError:
        return None


def parse_vcf_to_df(vcf_path: Union[Path, str], variant_type: str = "mixed", vaf_threshold: float = 0.0) -> pd.DataFrame:
    """
    Parses a VCF file into a pandas DataFrame.
    Extracts key INFO fields (GENE, HGVSc, HGVSp) and FORMAT fields (e.g., AF, DP).

    Args:
        vcf_path: Path to the VCF file.
        variant_type: 'SNV', 'INDEL', or 'mixed' (no filtering). Multi-allelic
            ALT records are split into one row per ALT allele.
        vaf_threshold: Drop variants whose VAF is known and below this value.
            Variants with an unknown VAF are kept (not enough info to exclude).
    """
    vcf_path = Path(vcf_path)
    variant_type = variant_type.upper()
    records = []
    
    with open(vcf_path, 'r') as f:
        for line in f:
            if line.startswith('##'):
                continue
            if line.startswith('#'):
                header = line.strip().split('\t')
                continue
            
            row = line.strip().split('\t')
            chrom = row[0]
            pos = int(row[1])
            id_ = row[2]
            ref = row[3]
            alts = row[4].split(',')  # multi-allelic: one or more ALT alleles
            qual = row[5]
            filter_ = row[6]
            info = row[7]

            # Parse INFO
            info_dict = {}
            for item in info.split(';'):
                if '=' in item:
                    k, v = item.split('=', 1)
                    info_dict[k] = v
                else:
                    info_dict[item] = True

            # Shared DP (per-record); AF is per-ALT and handled below.
            dp = None
            af_raw = None
            if len(row) > 9:
                format_keys = row[8].split(':')
                sample_vals = row[9].split(':')
                format_dict = dict(zip(format_keys, sample_vals))
                af_raw = format_dict.get('AF')
                if 'DP' in format_dict:
                    try:
                        dp = int(format_dict['DP'])
                    except ValueError:
                        pass

            # Fallback for DP if it's in INFO but not FORMAT
            if dp is None and 'DP' in info_dict:
                try:
                    dp = int(info_dict['DP'])
                except ValueError:
                    pass

            gene = info_dict.get('GENE', 'Unknown')
            hgvsc = info_dict.get('HGVSc', '')
            hgvsp = info_dict.get('HGVSp', '')

            # Emit one row per ALT allele, taking the matching AF value.
            af_values = af_raw.split(',') if af_raw else []
            for i, alt in enumerate(alts):
                vaf = _parse_first_float(af_values[i]) if i < len(af_values) else None

                # Filter by VAF threshold (unknown VAF is kept — not enough info to exclude).
                if vaf is not None and vaf < vaf_threshold:
                    continue

                vt = _classify_variant_type(ref, alt)
                if variant_type in ("SNV", "INDEL") and vt != variant_type:
                    continue

                records.append({
                    'chrom': chrom,
                    'pos': pos,
                    'ref': ref,
                    'alt': alt,
                    'gene': gene,
                    'hgvsc': hgvsc,
                    'hgvsp': hgvsp,
                    'vaf': vaf,
                    'dp': dp,
                    'variant_type': vt,
                    'filter': filter_
                })

    df = pd.DataFrame(records)
    return df
