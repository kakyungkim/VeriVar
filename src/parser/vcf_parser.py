import pandas as pd
from pathlib import Path
from typing import Optional, Union

def parse_vcf_to_df(vcf_path: Union[Path, str], variant_type: str = "mixed", vaf_threshold: float = 0.0) -> pd.DataFrame:
    """
    Parses a VCF file into a pandas DataFrame.
    Extracts key INFO fields (GENE, HGVSc, HGVSp) and FORMAT fields (e.g., AF, DP).
    """
    vcf_path = Path(vcf_path)
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
            alt = row[4]
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
            
            # Parse FORMAT and Sample
            vaf = None
            dp = None
            if len(row) > 9:
                format_keys = row[8].split(':')
                sample_vals = row[9].split(':')
                format_dict = dict(zip(format_keys, sample_vals))
                
                if 'AF' in format_dict:
                    try:
                        vaf = float(format_dict['AF'])
                    except ValueError:
                        pass
                
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

            # Filter by VAF threshold if requested
            if vaf is not None and vaf < vaf_threshold:
                continue
                
            gene = info_dict.get('GENE', 'Unknown')
            hgvsc = info_dict.get('HGVSc', '')
            hgvsp = info_dict.get('HGVSp', '')
            
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
                'filter': filter_
            })
            
    df = pd.DataFrame(records)
    return df
