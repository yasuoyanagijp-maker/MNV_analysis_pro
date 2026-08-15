"""Pilot case labels and local dual-read export paths (Desktop, not in-repo)."""

from pathlib import Path

G1_DIR = Path("/Users/yy/Desktop/octa_images_jpg/output_folder_2026_08_15")
G2_DIR = Path("/Users/yy/Desktop/octa_images_jpg/second_reader_output_2026_08_15")
INTEGRATED_DIR = Path("/Users/yy/Desktop/octa_images_jpg/integrated_output_2026_08_15")
G1_CSV = G1_DIR / "MNV_batch_20260815_094130.csv"
G2_CSV = G2_DIR / "MNV_batch_20260815_094130.csv"
INTEGRATED_RECHECK = INTEGRATED_DIR / "MNV_integrated_20260815_094445_recheck_list.csv"
SCALE_MM = 3.0
CASE_LABELS = {
    "20250409": "abe 20250409",
    "20260225": "abe 20260225",
    "20230314": "asai 20230314",
}
CASE_ORDER = ("abe 20250409", "abe 20260225", "asai 20230314")
CASE_SLUGS = {
    "abe 20250409": "abe_20250409",
    "abe 20260225": "abe_20260225",
    "asai 20230314": "asai_20230314",
}
