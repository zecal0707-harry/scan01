import os
import json
import shutil
import random
import string
import time
from datetime import datetime, timedelta

# ==========================================
# [설정] 대용량 모사 데이터 생성 설정
# ==========================================
ROOT_DIR = "D:\\MOCK_ROOT"
TARGET_FILM_RECIPES = 500 # Film Server에 생성할 레시피 개수
TARGET_SCAN_PATHS = 2000 # Scan Server에 생성할 데이터 경로 개수
TARGET_UNIQUE_LOTS = 300 # Lot History 구현을 위한 고유 Lot 개수

# 서버 설정
FILM_SERVER = {"name": "S_FILM_1", "root": "Film List", "prefix": "as"}
SCAN_SERVER = {"name": "S_SCAN_1", "root": "auto scan data"}

# 공정(Class Level 1) 및 세부 공정 목록
PROCESS_TYPES = ["THIN_FILM", "CMP", "PHOTO", "ETCH", "MI", "CLN"]
PROCESS_DETAILS = ["METALDEP1", "POLY_GATE", "VIA_HOLE", "STRIP", "GAP_FILL", "HARD_MASK"]

# ==========================================
# [Helper] Naming Rule Generators
# ==========================================
def get_random_date():
    """날짜 생성: (YYMMDD, YYYYMMDD)"""
    d = datetime(2024, 1, 1) + timedelta(days=random.randint(0, 365))
    return d.strftime("%y%m%d"), d.strftime("%Y%m%d")

def make_prod_code():
    """제품코드 규칙: 영2 + (영/수)1 + 영1 (예: AB1D, RS07)"""
    p1 = ''.join(random.choices(string.ascii_uppercase, k=2))
    p2 = random.choice(string.ascii_uppercase + string.digits)
    p3 = random.choice(string.ascii_uppercase)
    return f"{p1}{p2}{p3}"

def make_lot_id(prod_code):
    """Lot ID 규칙: [제품4] + [숫자4] + (옵션)[영문2]"""
    serial = ''.join(random.choices(string.digits, k=4))
    base = f"{prod_code}{serial}"
    # 20% 확률로 Split Lot (뒤에 영문 2자리)
    if random.random() < 0.2:
        base += ''.join(random.choices(string.ascii_uppercase, k=2))
    return base

def make_wafer_recipe(prod_code, proc_name):
    """Wafer Rec: [제품]_[공정]_[접미어]"""
    suffix = random.choice(["CM01", "CM02", "RUN1", "RE01", "TEST"])
    return f"{prod_code}_{proc_name}_{suffix}"

def make_film_recipe_name(prod_code, proc_name, date_short):
    """Film Rec: [제품(2or4)]_[공정]_[YYMMDD]"""
    # 30% 확률로 제품명을 2자리 약어로 단축
    p_name = prod_code if random.random() > 0.3 else prod_code[:2]
    return f"{p_name}_{proc_name}_{date_short}"

# ==========================================
# [Phase 1] Film Recipe 데이터 생성 (Source)
# ==========================================
def generate_film_server(root):
    print(f"--- [Step 1] Film Recipe ({TARGET_FILM_RECIPES}개) 생성 중 ---")
    
    recipes_index = {"folders": [], "by_recipe": {}}
    # 공정별 레시피 이름을 저장하여 Scan 데이터 생성 시 참조 (Matching 보장)
    recipe_db = {pt: [] for pt in PROCESS_TYPES}
    
    for i in range(1, TARGET_FILM_RECIPES + 1):
        folder_name = f"{FILM_SERVER['prefix']}{i:04d}" # as0001
        
        # 랜덤 속성 생성
        proc_type = random.choice(PROCESS_TYPES)
        proc_detail = random.choice(PROCESS_DETAILS)
        prod_code = make_prod_code()
        date_s, _ = get_random_date()
        
        # 규칙 적용: 레시피 이름 생성
        full_proc_name = f"{proc_type}_{proc_detail}" 
        rec_name = make_film_recipe_name(prod_code, full_proc_name, date_s)
        
        # DB에 등록 (이후 Scan 데이터가 가져다 씀)
        recipe_db[proc_type].append(rec_name)
        
        # 1. 물리 폴더 및 ini 파일 생성
        path = os.path.join(root, folder_name)
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, "strategy.ini"), 'w') as f:
            f.write(f"[Strategy]\nStrategyName = {rec_name}\nCreated = {datetime.now()}\n")
            
        # 2. 인덱스 데이터 구성
        logic_path = f"/{FILM_SERVER['root']}/{folder_name}"
        recipes_index["folders"].append(logic_path)
        
        if rec_name not in recipes_index["by_recipe"]:
            recipes_index["by_recipe"][rec_name] = []
        recipes_index["by_recipe"][rec_name].append(logic_path)
        
    print(" -> 완료.")
    return recipes_index, recipe_db

# ==========================================
# [Phase 2] Scan 데이터 생성 (History Simulation)
# ==========================================
def generate_scan_server(root, recipe_db):
    print(f"--- [Step 2] Scan Data ({TARGET_SCAN_PATHS}개) 생성 중 ---")
    
    lots_index = {}
    
    # Lot History 모사를 위해 'Active Lot Pool' 생성
    # 이 Lot들이 여러 공정(Class)을 돌아다니며 데이터를 쌓음
    active_lots = []
    for _ in range(TARGET_UNIQUE_LOTS):
        pc = make_prod_code()
        lid = make_lot_id(pc)
        active_lots.append({"id": lid, "prod": pc})
        
    count = 0
    while count < TARGET_SCAN_PATHS:
        # 기존 Lot 중 하나 선택
        lot_obj = random.choice(active_lots)
        lot_id = lot_obj['id']
        prod_code = lot_obj['prod']
        
        # 공정(Class Level 1) 랜덤 선택
        proc_type = random.choice(PROCESS_TYPES)
        
        # Class 상세 경로 구성 (Depth 1~5 랜덤 확장)
        class_parts = [proc_type] # Level 1
        
        # Level 2~5 추가 확률
        if random.random() < 0.6: 
            class_parts.append(random.choice(["module", "FULL", "PROD", prod_code]))
        if random.random() < 0.4: 
            class_parts.append("BS")
        if random.random() < 0.2:
            class_parts.append("TEST_GRP")
            
        # [중요] 해당 공정(proc_type)에 맞는 Film Recipe가 DB에 있는지 확인
        available_recs = recipe_db.get(proc_type, [])
        if not available_recs: continue # 해당 공정 레시피가 없으면 스킵 (재시도)
        
        # 매칭되는 레시피 하나 선택 (Link 보장)
        used_film_rec = random.choice(available_recs)
        
        # Wafer Recipe 이름 생성 (제품코드 일치)
        # (Film Recipe 이름에서 공정명 일부를 유추하거나 랜덤 배정)
        proc_detail_sim = random.choice(PROCESS_DETAILS)
        full_proc = f"{proc_type}_{proc_detail_sim}"
        wafer_rec = make_wafer_recipe(prod_code, full_proc)
        
        _, date_l = get_random_date()
        
        # 1. 물리적 경로 생성
        # D:\...\Class\WaferRec\LotID\FilmRec\Date
        rel_path = os.path.join(*class_parts, wafer_rec, lot_id, used_film_rec, date_l)
        full_path = os.path.join(root, rel_path)
        
        if os.path.exists(full_path): continue # 중복 경로 방지
        os.makedirs(full_path, exist_ok=True)
        
        # 2. 결과 파일 생성
        with open(os.path.join(full_path, "Result.csv"), 'w') as f:
            f.write(f"ScanData,{lot_id},{used_film_rec},{datetime.now()}")
            
        # 3. 인덱스 데이터 구성
        logic_class = "/".join(class_parts)
        logic_path = f"/{SCAN_SERVER['root']}/{logic_class}/{wafer_rec}/{lot_id}"
        
        if lot_id not in lots_index: lots_index[lot_id] = []
        lots_index[lot_id].append(logic_path)
        
        count += 1
        
    print(" -> 완료.")
    return lots_index

# ==========================================
# [Main] 실행
# ==========================================
if __name__ == "__main__":
    start_ts = time.time()
    
    # 기존 데이터 삭제
    if os.path.exists(ROOT_DIR): shutil.rmtree(ROOT_DIR)
    
    film_root = os.path.join(ROOT_DIR, FILM_SERVER['root'])
    scan_root = os.path.join(ROOT_DIR, SCAN_SERVER['root'])
    
    # 1. 레시피 데이터 생성
    rec_idx, rec_db = generate_film_server(film_root)
    
    # 2. 스캔 데이터 생성
    lots_idx = generate_scan_server(scan_root, rec_db)
    
    # 3. JSON 파일 저장 (Scanner 출력 모사)
    os.makedirs("out/required", exist_ok=True)
    os.makedirs("out/recipes", exist_ok=True)
    
    with open(f"out/recipes/{FILM_SERVER['name']}_recipes_index.json", 'w') as f:
        json.dump(rec_idx, f, indent=2)
    with open(f"out/required/{SCAN_SERVER['name']}_lots_index.json", 'w') as f:
        json.dump(lots_idx, f, indent=2)
        
    print(f"\n[SUCCESS] Mock Environment Created.")
    print(f" - Path: {ROOT_DIR}")
    print(f" - Time: {time.time()-start_ts:.2f} sec")
