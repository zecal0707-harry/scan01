
import logging
import sys
import os
import json
from scanner.scanner.utils import load_json

logging.basicConfig(level=logging.ERROR)

def check_indices():
    lot_idx_path = "out/required/LOCAL_SCAN_lots_index.json"
    film_idx_path = "out/required/LOCAL_SCAN_films_index.json"
    
    lots_doc = load_json(lot_idx_path, {})
    idx = lots_doc.get("lots_index") or {}
    
    print(f"Lots Index Size: {len(idx)}")
    if "POFX8999" in idx:
        print(f"POFX8999 in Lots Index: {idx['POFX8999']}")
    else:
        print("POFX8999 NOT in Lots Index")
        # Check patterns
        for k in idx.keys():
            if "POFX8999" in k:
                print(f"Found partial match: {k}")

    film_doc = load_json(film_idx_path, {})
    f_idx = film_doc.get("films_index") or {}
    print(f"Films Index Size: {len(f_idx)}")
    
    # Check if paths for POFX8999 are in films index
    if "POFX8999" in idx:
        paths = idx["POFX8999"]
        for p in paths:
            if p in f_idx:
                 print(f"Path '{p}' FOUND in Films Index. Num values: {len(f_idx[p])}")
                 print(f"Values: {f_idx[p]}")
            else:
                 print(f"Path '{p}' NOT FOUND in Films Index")
                 # Check partial match/separator mismatch
                 p_alt_1 = p.replace("/", "\\")
                 p_alt_2 = p.replace("\\", "/")
                 if p_alt_1 in f_idx:
                     print(f"Path '{p_alt_1}' FOUND (backslash)")
                 if p_alt_2 in f_idx:
                     print(f"Path '{p_alt_2}' FOUND (slash)")

if __name__ == "__main__":
    check_indices()
