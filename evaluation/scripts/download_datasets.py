"""Download and prepare benchmark datasets for GMEE evaluation.

Publicly available datasets downloaded:
1. LIAR (William Wang, ACL 2017) -> liar_test.csv (columns: id, statement, label)
2. ClaimBuster (Arslan et al., 2020 / Zenodo 3609356) -> claimbuster_test.csv (columns: text, cfs_score)
3. MultiFC (Augenstein et al., EMNLP 2019) -> multifc_test.csv (columns: claimID, claim, label)
4. FEVER dev set (Thorne et al., NAACL 2018) -> fever_dev.jsonl (fields: claim, label)

Produces:
- download_manifest.json with {dataset, filename, rows, downloaded_at}
"""

import argparse
import datetime
import io
import json
import os
import sys
import zipfile
from typing import Any, Dict, List

import pandas as pd
import requests

USER_AGENT = "GMEE-Evaluation-Harness/1.0 (Academic Research)"
REQUEST_TIMEOUT = 60


def download_liar(output_dir: str) -> Dict[str, Any]:
    """Download LIAR test set and format as CSV (id, statement, label)."""
    urls = [
        "https://sites.cs.ucsb.edu/~william/data/liar_dataset.zip",
        "https://www.cs.ucsb.edu/~william/data/liar_dataset.zip",
    ]
    resp = None
    for url in urls:
        try:
            r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
            if r.status_code == 200:
                resp = r
                break
        except Exception:
            continue

    if resp is None or resp.status_code != 200:
        raise RuntimeError(f"Failed to download LIAR dataset from {urls}")

    z = zipfile.ZipFile(io.BytesIO(resp.content))
    test_tsv_bytes = z.read("test.tsv")
    df_raw = pd.read_csv(io.BytesIO(test_tsv_bytes), sep="\t", header=None, quoting=3)

    # test.tsv columns:
    # 0: id (e.g., 11972.json)
    # 1: label (e.g., true, false, half-true, mostly-true, barely-true, pants-fire)
    # 2: statement
    df_liar = pd.DataFrame({
        "id": df_raw[0].astype(str),
        "statement": df_raw[2].astype(str),
        "label": df_raw[1].astype(str),
    })

    filename = "liar_test.csv"
    output_path = os.path.join(output_dir, filename)
    df_liar.to_csv(output_path, index=False, encoding="utf-8")

    return {
        "dataset": "liar",
        "filename": filename,
        "rows": len(df_liar),
        "downloaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def download_claimbuster(output_dir: str) -> Dict[str, Any]:
    """Download ClaimBuster ground truth test set from Zenodo record 3609356."""
    url = "https://zenodo.org/api/records/3609356/files/groundtruth.csv/content"
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
    if r.status_code != 200:
        raise RuntimeError(f"Failed to download ClaimBuster dataset: HTTP {r.status_code}")

    df_raw = pd.read_csv(io.BytesIO(r.content))

    # In ClaimBuster ground truth:
    # Verdict == 1: Check-worthy Factual Statement (CFS) -> 1.0
    # Verdict == 0 (UFS) or -1 (NFS): Not check-worthy -> 0.0
    df_cb = pd.DataFrame({
        "text": df_raw["Text"].astype(str),
        "cfs_score": (df_raw["Verdict"] == 1).astype(float),
    })

    filename = "claimbuster_test.csv"
    output_path = os.path.join(output_dir, filename)
    df_cb.to_csv(output_path, index=False, encoding="utf-8")

    return {
        "dataset": "claimbuster",
        "filename": filename,
        "rows": len(df_cb),
        "downloaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def download_multifc(output_dir: str) -> Dict[str, Any]:
    """Download MultiFC evaluation set with ground truth labels."""
    # Hugging Face mirror contains the labeled evaluation split (dev.csv)
    # The competition test.csv has withheld labels, so dev.csv provides ground-truth
    url = "https://huggingface.co/datasets/pszemraj/multi_fc/resolve/main/dev.csv"
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
    if r.status_code != 200:
        raise RuntimeError(f"Failed to download MultiFC dataset: HTTP {r.status_code}")

    df_raw = pd.read_csv(io.BytesIO(r.content))
    df_clean = df_raw[["claimID", "claim", "label"]].dropna(subset=["claim", "label"]).copy()

    filename = "multifc_test.csv"
    output_path = os.path.join(output_dir, filename)
    df_clean.to_csv(output_path, index=False, encoding="utf-8")

    return {
        "dataset": "multifc",
        "filename": filename,
        "rows": len(df_clean),
        "downloaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def download_fever(output_dir: str) -> Dict[str, Any]:
    """Download FEVER shared task dev set (19,998 rows)."""
    urls = [
        "https://fever.ai/download/fever/shared_task_dev.jsonl",
        "https://s3-eu-west-1.amazonaws.com/fever.data/shared_task_dev.jsonl",
    ]
    resp = None
    for url in urls:
        try:
            r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT, stream=True)
            if r.status_code == 200:
                resp = r
                break
        except Exception:
            continue

    if resp is None or resp.status_code != 200:
        raise RuntimeError(f"Failed to download FEVER dataset from {urls}")

    filename = "fever_dev.jsonl"
    output_path = os.path.join(output_dir, filename)

    row_count = 0
    with open(output_path, "w", encoding="utf-8") as f_out:
        for line in resp.iter_lines():
            if not line:
                continue
            item = json.loads(line.decode("utf-8"))
            # Retain required fields: claim, label (and original id / evidence for reference)
            record = {
                "id": item.get("id"),
                "claim": item.get("claim"),
                "label": item.get("label"),
            }
            f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
            row_count += 1

    return {
        "dataset": "fever",
        "filename": filename,
        "rows": row_count,
        "downloaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Download benchmark datasets for GMEE evaluation.")
    parser.add_argument(
        "--output",
        type=str,
        default="evaluation/data/baselines/",
        help="Directory to save downloaded datasets (default: evaluation/data/baselines/)",
    )
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)
    manifest: List[Dict[str, Any]] = []

    downloaders = [
        ("LIAR", download_liar),
        ("ClaimBuster", download_claimbuster),
        ("MultiFC", download_multifc),
        ("FEVER", download_fever),
    ]

    print("=" * 65)
    print("GMEE Benchmark Dataset Downloader")
    print("=" * 65)

    for name, func in downloaders:
        print(f"Downloading {name}...", end=" ", flush=True)
        try:
            meta = func(args.output)
            manifest.append(meta)
            print(f"OK ({meta['rows']} rows -> {meta['filename']})")
        except Exception as e:
            print(f"FAILED: {e}")
            sys.exit(1)

    # Save manifest
    manifest_path = os.path.join(args.output, "download_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print("=" * 65)
    print(f"Download manifest written to: {manifest_path}")
    print(f"Total datasets prepared: {len(manifest)}")
    print("=" * 65)


if __name__ == "__main__":
    main()
