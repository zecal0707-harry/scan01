#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Forward Spectrum Generator for EMVE scenarios.

Reads scenario JSON, loads material models, computes Psi/Delta (and optional reflectance),
and writes CSV + metadata. Supports scenario file or folder (recursive).
"""

import argparse
import json
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Iterable

import numpy as np

# Physical constants
HC_EV_NM = 1239.841984  # eV*nm


# -----------------------------
# Utilities
# -----------------------------
def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)


def deg2rad(x): return np.deg2rad(x)
def rad2deg(x): return np.rad2deg(x)


def parse_keyval_lines(text: str) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            try:
                out[k.strip().lower()] = float(v.strip())
            except ValueError:
                continue
    return out


# -----------------------------
# Material Models
# -----------------------------
@dataclass
class NKTable:
    wavelength_nm: np.ndarray
    n: np.ndarray
    k: np.ndarray

    def nk(self, wl_nm: np.ndarray) -> np.ndarray:
        wl_nm = np.asarray(wl_nm, dtype=float)
        n_i = np.interp(wl_nm, self.wavelength_nm, self.n)
        k_i = np.interp(wl_nm, self.wavelength_nm, self.k)
        return n_i + 1j * k_i


def load_nk_table(path: str) -> NKTable:
    """
    Supports:
    1) Text NK tables in wavelength-nm n k format
    2) Text NK tables in eV e1 e2 format (jaw .mat files)
    3) MATLAB v5 binary .mat (requires scipy)
    """
    with open(path, "rb") as f:
        head = f.read(64)

    if head.startswith(b"MATLAB 5.0 MAT-file"):
        try:
            from scipy.io import loadmat  # type: ignore
        except Exception as e:  # pragma: no cover - scipy optional
            raise RuntimeError("scipy is required to load MATLAB binary .mat files") from e
        mat = loadmat(path)
        wl = None
        for key in ["wavelength_nm", "wl_nm", "lambda_nm", "wl"]:
            if key in mat:
                wl = np.ravel(mat[key]).astype(float)
                break
        if wl is None:
            raise KeyError(f"Cannot find wavelength key in {path}. Keys: {list(mat.keys())}")
        n = None
        for key in ["n", "n_data"]:
            if key in mat:
                n = np.ravel(mat[key]).astype(float)
                break
        if n is None:
            raise KeyError(f"Cannot find n key in {path}. Keys: {list(mat.keys())}")
        k = None
        for key in ["k", "k_data"]:
            if key in mat:
                k = np.ravel(mat[key]).astype(float)
                break
        if k is None:
            raise KeyError(f"Cannot find k key in {path}. Keys: {list(mat.keys())}")
        return NKTable(wavelength_nm=wl, n=n, k=k)

    txt = read_text(path)
    lines = [ln.strip() for ln in txt.splitlines() if ln.strip() and not ln.strip().startswith("#")]

    # Detect eV/e1/e2 header (jaw .mat text files)
    ev_mode = len(lines) >= 3 and lines[1].lower() == "ev" and lines[2].lower().startswith("e1")
    if ev_mode:
        data_lines = lines[3:]
        rows = []
        for ln in data_lines:
            parts = re.split(r"[\s,]+", ln.strip())
            if len(parts) < 3:
                continue
            try:
                e_ev = float(parts[0]); e1 = float(parts[1]); e2 = float(parts[2])
                rows.append((e_ev, e1, e2))
            except ValueError:
                continue
        if not rows:
            raise ValueError(f"Failed to parse e1/e2 NK table from {path}")
        arr = np.array(rows, dtype=float)
        wl_nm = HC_EV_NM / np.maximum(arr[:, 0], 1e-12)
        eps = arr[:, 1] + 1j * arr[:, 2]
        nk = np.sqrt(eps)
        order = np.argsort(wl_nm)
        return NKTable(wavelength_nm=wl_nm[order], n=np.real(nk)[order], k=np.imag(nk)[order])

    # Fallback: wavelength_nm n k
    rows: List[List[float]] = []
    rows_by_angle: Dict[float, List[List[float]]] = {}
    for ln in lines:
        parts = re.split(r"[\s,]+", ln.strip())
        if len(parts) < 3:
            continue
        try:
            wl = float(parts[0]); n = float(parts[1]); k = float(parts[2])
            rows.append((wl, n, k))
        except ValueError:
            continue
    if not rows:
        raise ValueError(f"Failed to parse NK table from {path}")
    arr = np.array(rows, dtype=float)
    order = np.argsort(arr[:, 0])
    return NKTable(wavelength_nm=arr[order, 0], n=arr[order, 1], k=arr[order, 2])


@dataclass
class CauchyModel:
    A: float
    B: float
    C: float

    def nk(self, wl_nm: np.ndarray) -> np.ndarray:
        wl_nm = np.asarray(wl_nm, dtype=float)
        lam_um = wl_nm / 1000.0
        n = self.A + self.B / (lam_um ** 2) + self.C / (lam_um ** 4)
        return n + 0j


def load_cauchy_param_file(path: str) -> CauchyModel:
    kv = parse_keyval_lines(read_text(path))
    A = kv.get("a", kv.get("a_n"))
    B = kv.get("b", kv.get("b_n"))
    C = kv.get("c", kv.get("c_n", 0.0))
    if A is None or B is None:
        raise ValueError(f"Missing A/B in cauchy file {path}")
    return CauchyModel(A=A, B=B, C=C)


@dataclass
class DrudeModel:
    ep_eV: float
    gamma_eV: float
    eps_inf: float = 1.0

    def epsilon(self, E_eV: np.ndarray) -> np.ndarray:
        E = np.maximum(E_eV, 1e-9)
        return self.eps_inf - (self.ep_eV ** 2) / (E ** 2 + 1j * self.gamma_eV * E)

    def nk(self, wl_nm: np.ndarray) -> np.ndarray:
        E = HC_EV_NM / np.maximum(wl_nm, 1e-9)
        eps = self.epsilon(E)
        return np.sqrt(eps)


def load_drude_param_file(path: str) -> DrudeModel:
    kv = parse_keyval_lines(read_text(path))
    ep = kv.get("ep_ev", kv.get("ep"))
    gamma = kv.get("gamma_ev", kv.get("gamma"))
    eps_inf = kv.get("eps_inf", kv.get("einf", 1.0))
    if ep is None or gamma is None:
        raise ValueError(f"Drude file {path} must include Ep/Gamma")
    return DrudeModel(ep_eV=ep, gamma_eV=gamma, eps_inf=eps_inf)


@dataclass
class TL2GenoscModel:
    amp: float
    en: float
    c: float
    eg: float
    ep1: float = 0.0
    ap1: float = 0.0
    ep2: float = 0.0
    ap2: float = 0.0
    e1_offset: float = 0.0
    eps_inf: float = 1.0
    kk_Emin: float = 0.5
    kk_Emax: float = 25.0
    kk_N: int = 2000
    pole_gamma_eV: float = 1e-3

    def epsilon2_tauc_lorentz(self, E: np.ndarray) -> np.ndarray:
        A, E0, C, Eg = self.amp, self.en, self.c, self.eg
        eps2 = np.zeros_like(E, dtype=float)
        mask = E > Eg
        Em = E[mask]
        num = A * C * E0 * (Em - Eg) ** 2
        den = Em * ((Em ** 2 - E0 ** 2) ** 2 + (C ** 2) * (Em ** 2))
        eps2[mask] = num / np.maximum(den, 1e-30)
        return eps2

    def epsilon_poles(self, E: np.ndarray) -> np.ndarray:
        eps = np.zeros_like(E, dtype=complex)
        for ep, ap in [(self.ep1, self.ap1), (self.ep2, self.ap2)]:
            if ap == 0 or ep == 0:
                continue
            eps += ap * (ep ** 2) / ((ep ** 2 - E ** 2) - 1j * self.pole_gamma_eV * E)
        return eps

    def epsilon(self, E_eval: np.ndarray) -> np.ndarray:
        Egrid = np.linspace(self.kk_Emin, self.kk_Emax, self.kk_N)
        eps2_grid = self.epsilon2_tauc_lorentz(Egrid)
        eps1 = np.zeros_like(E_eval, dtype=float)
        for i, E0 in enumerate(E_eval):
            denom = (Egrid ** 2 - E0 ** 2)
            denom = np.where(np.abs(denom) < 1e-9, np.sign(denom) * 1e-9 + 1e-9, denom)
            integrand = (Egrid * eps2_grid) / denom
            eps1[i] = (2.0 / np.pi) * np.trapezoid(integrand, Egrid)
        eps_tl = (eps1 + self.e1_offset + self.eps_inf) + 1j * self.epsilon2_tauc_lorentz(E_eval)
        eps = eps_tl + self.epsilon_poles(E_eval)
        return eps

    def nk(self, wl_nm: np.ndarray) -> np.ndarray:
        E = HC_EV_NM / np.maximum(wl_nm, 1e-9)
        eps = self.epsilon(E)
        return np.sqrt(eps)


def parse_tl2_genosc(path: str) -> Dict[str, List[float]]:
    lines = [ln.strip() for ln in read_text(path).replace("\r\n", "\n").split("\n")]
    lines = [ln for ln in lines if ln]
    if len(lines) < 3 or lines[1].upper() != "GENOSC":
        raise ValueError(f"{path} is not a GENOSC TL2 file")

    def next_values(start: int) -> Tuple[List[float], int]:
        idx = start
        while idx < len(lines) and not lines[idx]:
            idx += 1
        if idx >= len(lines):
            return [], idx
        try:
            vals = [float(x) for x in lines[idx].split()]
        except ValueError:
            vals = []
        return vals, idx + 1

    idx = 2
    pole_vals, idx = next_values(idx)
    cfg_vals, idx = next_values(idx)
    tl_vals, idx = next_values(idx)
    tl2_vals, idx = next_values(idx)

    while len(pole_vals) < 6:
        pole_vals.append(0.0)

    return {
        "pole": pole_vals,
        "cfg": cfg_vals,
        "tl": tl_vals,
        "tl_extra": tl2_vals,
    }


def load_tl2_model(path: str, nk_fallback: Optional[NKTable] = None) -> object:
    try:
        parsed = parse_tl2_genosc(path)
        pole = parsed["pole"]
        tl = parsed["tl"]
        extra = parsed["tl_extra"]

        amp = tl[-2] if len(tl) >= 2 else 0.0
        en = tl[-1] if tl else 0.0
        c_val = tl[-3] if len(tl) >= 3 else (extra[0] if extra else 0.0)
        eg_val = extra[1] if len(extra) >= 2 else 0.0
        eps_inf = tl[0] if tl else 1.0

        ep1, ap1, ep2, ap2, e1_offset, _ = pole[:6]
        # Guard against pathological pole amplitudes
        ap1 = 0.0 if abs(ap1) > 1e6 else ap1
        ap2 = 0.0 if abs(ap2) > 1e6 else ap2

        return TL2GenoscModel(
            amp=amp or 0.0,
            en=en or 0.0,
            c=c_val,
            eg=eg_val,
            ep1=ep1,
            ap1=ap1,
            ep2=ep2,
            ap2=ap2,
            e1_offset=e1_offset,
            eps_inf=eps_inf if eps_inf != 0 else 1.0,
        )
    except Exception:
        if nk_fallback is not None:
            return nk_fallback
        raise


# -----------------------------
# EMA (Bruggeman)
# -----------------------------
def bruggeman_eps(eps_a: np.ndarray, eps_b: np.ndarray, fa: float, max_iter=100, tol=1e-10) -> np.ndarray:
    eps = fa * eps_a + (1 - fa) * eps_b
    for _ in range(max_iter):
        f = fa * (eps_a - eps) / (eps_a + 2 * eps) + (1 - fa) * (eps_b - eps) / (eps_b + 2 * eps)
        df = fa * (-(eps_a + 2 * eps) - 2 * (eps_a - eps)) / (eps_a + 2 * eps) ** 2 \
           + (1 - fa) * (-(eps_b + 2 * eps) - 2 * (eps_b - eps)) / (eps_b + 2 * eps) ** 2
        step = f / np.where(np.abs(df) < 1e-30, 1e-30, df)
        eps_new = eps - step
        if np.max(np.abs(eps_new - eps)) < tol:
            eps = eps_new
            break
        eps = eps_new
    return eps


# -----------------------------
# Transfer Matrix (isotropic)
# -----------------------------
def multilayer_rp_rs(wl_nm: float, angle_deg: float, n_list: List[complex], d_list_nm: List[float]) -> Tuple[complex, complex]:
    lam = wl_nm * 1e-9
    k0 = 2.0 * np.pi / lam
    theta0 = deg2rad(angle_deg)
    n0 = n_list[0]
    sin0 = np.sin(theta0)

    cos_t = []
    for nj in n_list:
        sj = (n0 * sin0) / nj
        cosj = np.sqrt(1 - sj * sj)
        cos_t.append(cosj)

    def q_s(nj, cosj): return nj * cosj
    def q_p(nj, cosj): return cosj / nj

    def stabilize_phase(delta_val: complex) -> complex:
        real_part = np.remainder(np.real(delta_val), 2 * np.pi)
        imag_part = np.clip(np.imag(delta_val), -100.0, 100.0)
        return real_part + 1j * imag_part

    def char_matrix(pol: str):
        M = np.array([[1 + 0j, 0 + 0j], [0 + 0j, 1 + 0j]])
        for idx in range(1, len(n_list) - 1):
            nj = n_list[idx]
            cosj = cos_t[idx]
            dj = d_list_nm[idx - 1] * 1e-9
            delta = stabilize_phase(k0 * nj * cosj * dj)
            qj = q_s(nj, cosj) if pol == "s" else q_p(nj, cosj)
            m11 = np.cos(delta)
            m12 = 1j * np.sin(delta) / qj
            m21 = 1j * qj * np.sin(delta)
            m22 = np.cos(delta)
            M = M @ np.array([[m11, m12], [m21, m22]])
        return M

    nS = n_list[-1]
    cosS = cos_t[-1]

    def refl(pol: str):
        M = char_matrix(pol)
        q0 = q_s(n0, cos_t[0]) if pol == "s" else q_p(n0, cos_t[0])
        qS = q_s(nS, cosS) if pol == "s" else q_p(nS, cosS)
        A = M[0, 0] + M[0, 1] * qS
        B = M[1, 0] + M[1, 1] * qS
        r = (q0 * A - B) / (q0 * A + B)
        return r

    rs = refl("s")
    rp = refl("p")
    return rp, rs


def psi_delta_from_r(rp: complex, rs: complex) -> Tuple[float, float]:
    rho = rp / rs
    psi = np.arctan(np.abs(rho))
    delta = np.angle(rho)
    return float(rad2deg(psi)), float(rad2deg(delta))


# -----------------------------
# Material library + stack
# -----------------------------
class MaterialLibrary:
    def __init__(self, material_dir: str):
        self.material_dir = material_dir
        self.cache: Dict[str, object] = {}
        self.file_index: Dict[str, str] = {}
        for root, _, files in os.walk(material_dir):
            for fn in files:
                self.file_index[fn.lower()] = os.path.join(root, fn)

    def resolve_path(self, filename: str) -> str:
        if os.path.isabs(filename) and os.path.exists(filename):
            return filename
        p = os.path.join(self.material_dir, filename)
        if os.path.exists(p):
            return p
        key = filename.lower()
        if key in self.file_index:
            return self.file_index[key]
        raise FileNotFoundError(f"Material file not found: {filename}")

    def load_model(self, model_type: str, material_file: str):
        key = f"{model_type}::{material_file}"
        if key in self.cache:
            return self.cache[key]

        if material_file is None or str(material_file).lower() in ["air", "air.mat"]:
            model = ("constant", 1.0 + 0j)
            self.cache[key] = model
            return model

        try:
            path = self.resolve_path(material_file)
        except FileNotFoundError:
            if model_type == "nk_table":
                model = ("constant", 1.0 + 0j)
                self.cache[key] = model
                return model
            raise

        if model_type == "nk_table":
            model = load_nk_table(path)
        elif model_type == "cauchy_param_file":
            model = load_cauchy_param_file(path)
        elif model_type == "drude_param_file":
            model = load_drude_param_file(path)
        elif model_type == "tl2_genosc":
            # try TL2, fall back to matching NK table if present
            base = os.path.splitext(material_file)[0]
            nk_name = base.replace("_tl2", "") + ".mat"
            nk_fallback = None
            if nk_name.lower() in self.file_index:
                nk_fallback = load_nk_table(self.file_index[nk_name.lower()])
            model = load_tl2_model(path, nk_fallback=nk_fallback)
        else:
            raise ValueError(f"Unknown model_type: {model_type}")

        self.cache[key] = model
        return model

    def nk(self, model_type: str, material_file: str, wl_nm: np.ndarray) -> np.ndarray:
        model = self.load_model(model_type, material_file)
        if isinstance(model, tuple) and model[0] == "constant":
            return np.full_like(wl_nm, model[1], dtype=complex)
        if isinstance(model, NKTable):
            return model.nk(wl_nm)
        if isinstance(model, CauchyModel):
            return model.nk(wl_nm)
        if isinstance(model, DrudeModel):
            return model.nk(wl_nm)
        if isinstance(model, TL2GenoscModel):
            return model.nk(wl_nm)
        raise TypeError(f"Unsupported model object: {type(model)}")


# -----------------------------
# Spectrum generation
# -----------------------------
def generate_spectrum(scenario: dict, material_dir: str, outdir: str) -> str:
    ensure_dir(outdir)
    lib = MaterialLibrary(material_dir)

    sim = scenario["simulation"]
    angles = sim["angles_deg"]
    wl = np.arange(sim["wavelength_nm"]["start"], sim["wavelength_nm"]["end"] + 1e-9, sim["wavelength_nm"]["step"], dtype=float)
    noise = float(sim.get("noise_sigma", 0.0))
    seed = int(sim.get("seed", 0))
    rng = np.random.default_rng(seed)

    sys_angle = float(sim.get("systematics", {}).get("angle_offset_deg", {}).get("value", 0.0))
    sys_wl = float(sim.get("systematics", {}).get("wavelength_shift_nm", {}).get("value", 0.0))

    instrument = sim.get("instrument", {})
    psi_bias = float(instrument.get("psi_bias_deg", {}).get("value", 0.0)) if isinstance(instrument, dict) else 0.0
    delta_bias = float(instrument.get("delta_bias_deg", {}).get("value", 0.0)) if isinstance(instrument, dict) else 0.0
    refl_cfg = instrument.get("reflectance", {}) if isinstance(instrument, dict) else {}
    reflectance_enabled = bool(refl_cfg.get("enabled", False))
    refl_noise = float(refl_cfg.get("noise_sigma", 0.0)) if reflectance_enabled else 0.0

    stack = scenario["stack"]
    ambient = stack["ambient"]
    substrate = stack["substrate"]
    layers = stack["layers"]

    wl_eff = wl + sys_wl

    ambient_file = ambient.get("material_file") or "air.mat"
    nk_ambient = lib.nk("nk_table", ambient_file, wl_eff)
    nk_sub = lib.nk(substrate["model_type"], substrate["material_file"], wl_eff)

    layer_nk_list: List[np.ndarray] = []
    layer_d_list: List[float] = []

    for lay in layers:
        if lay.get("type") == "roughness":
            comps = lay["ema"]["components"]
            cA, cB = comps[0], comps[1]
            cA_model = cA.get("model_type") or "nk_table"
            cA_file = cA.get("material_file") or "air.mat"
            cB_model = cB.get("model_type") or "nk_table"
            cB_file = cB.get("material_file") or "air.mat"
            nkA = lib.nk(cA_model, cA_file, wl_eff)
            nkB = lib.nk(cB_model, cB_file, wl_eff)
            epsA = nkA ** 2
            epsB = nkB ** 2
            fa = float(cA["fraction"]["value"])
            eps_eff = bruggeman_eps(epsA, epsB, fa)
            nk_eff = np.sqrt(eps_eff)
            layer_nk_list.append(nk_eff)
            layer_d_list.append(float(lay["thickness"]["value"]))
        else:
            l_model = lay.get("model_type") or "nk_table"
            l_file = lay.get("material_file") or "air.mat"
            nkL = lib.nk(l_model, l_file, wl_eff)
            layer_nk_list.append(nkL)
            layer_d_list.append(float(lay["thickness"]["value"]))

    # Backside handling (optional, coherent approximation)
    backside_cfg = scenario.get("fitting", {}).get("backside", {})
    backside_enabled = bool(backside_cfg.get("enabled", False) and substrate.get("thickness_nm"))
    backside_rough_nm = float(backside_cfg.get("backside_roughness_nm", 0.0)) if backside_enabled else 0.0
    backside_ambient_file = backside_cfg.get("ambient_material_file", "air.mat") if backside_enabled else None

    rows: List[List[float]] = []
    rows_by_angle: Dict[float, List[List[float]]] = {}

    for ang in angles:
        ang_val = float(ang)
        ang_eff = ang_val + sys_angle
        per_angle_rows: List[List[float]] = []
        for i in range(len(wl_eff)):
            n_list = [nk_ambient[i]] + [lnk[i] for lnk in layer_nk_list]
            d_list_nm = list(layer_d_list)

            if backside_enabled:
                sub_thick_entry = substrate.get("thickness_nm", 0.0)
                if isinstance(sub_thick_entry, dict):
                    sub_thick = float(sub_thick_entry.get("value", 0.0))
                else:
                    sub_thick = float(sub_thick_entry)
                n_sub_layer = nk_sub[i]
                backside_n = lib.nk("nk_table", backside_ambient_file, np.array([wl_eff[i]]))[0] if backside_ambient_file else 1.0 + 0j
                rough_thick = backside_rough_nm
                # Substrate as finite layer + backside roughness EMA to backside ambient
                n_list.append(n_sub_layer)
                d_list_nm.append(sub_thick)
                if rough_thick > 0:
                    eps_eff = bruggeman_eps(n_sub_layer ** 2, backside_n ** 2, 0.5)
                    n_eff = np.sqrt(eps_eff)
                    n_list.append(n_eff)
                    d_list_nm.append(rough_thick)
                n_list.append(backside_n)
            else:
                n_list.append(nk_sub[i])

            rp, rs = multilayer_rp_rs(wl_eff[i], ang_eff, n_list, d_list_nm)
            psi, delta = psi_delta_from_r(rp, rs)
            if noise > 0:
                psi += float(rng.normal(0.0, noise))
                delta += float(rng.normal(0.0, noise))
            psi += psi_bias
            delta += delta_bias

            row = [wl[i], ang, psi, delta]
            if reflectance_enabled:
                R = 0.5 * (np.abs(rp) ** 2 + np.abs(rs) ** 2)
                if refl_noise > 0:
                    R += float(rng.normal(0.0, refl_noise))
                row.append(R)
            rows.append(row)
            per_angle_rows.append(row)
        rows_by_angle[ang_val] = per_angle_rows

    columns = ["wavelength_nm", "angle_deg", "psi_deg", "delta_deg"]
    if reflectance_enabled:
        columns.append("reflectance")

    out_csv = os.path.join(outdir, f"{scenario['scenario_id']}_psi_delta.csv")
    with open(out_csv, "w", encoding="utf-8") as f:
        f.write(",".join(columns) + "\n")
        fmt = "{:.6f},{:.3f},{:.8f},{:.8f}"
        for r in rows:
            if reflectance_enabled:
                f.write(fmt.format(r[0], r[1], r[2], r[3]) + f",{r[4]:.8f}\n")
            else:
                f.write(fmt.format(r[0], r[1], r[2], r[3]) + "\n")

    # Additional outputs matching refellips-style formats
    for ang_val, ang_rows in rows_by_angle.items():
        ref_columns = ["Wavelength(nm)", "Psi", "Delta"]
        ref_csv = os.path.join(outdir, f"{scenario['scenario_id']}_angle{ang_val:.1f}_refellips.csv")
        with open(ref_csv, "w", encoding="utf-8") as f:
            f.write(",".join(ref_columns) + "\n")
            for r in ang_rows:
                f.write(f"{r[0]:.6f},{r[2]:.8f},{r[3]:.8f}\n")

        mea_columns = ["wl_nm", "AOI_deg", "Psi_deg", "Delta_deg"]
        mea_txt = os.path.join(outdir, f"{scenario['scenario_id']}_angle{ang_val:.1f}_mea.txt")
        with open(mea_txt, "w", encoding="utf-8") as f:
            f.write("\t".join(mea_columns) + "\n")
            for r in ang_rows:
                f.write(f"{r[0]:.6f}\t{r[1]:.3f}\t{r[2]:.8f}\t{r[3]:.8f}\n")

    out_meta = os.path.join(outdir, f"{scenario['scenario_id']}_meta.json")
    with open(out_meta, "w", encoding="utf-8") as f:
        json.dump({
            "scenario_id": scenario["scenario_id"],
            "level": scenario.get("level"),
            "recipe_name": scenario.get("recipe_name"),
            "material_dir": os.path.abspath(material_dir),
            "noise_sigma": noise,
            "seed": seed,
            "systematics": sim.get("systematics", {}),
            "instrument": instrument,
            "output_csv": os.path.abspath(out_csv),
            "columns": columns,
        }, f, ensure_ascii=False, indent=2)

    return out_csv


# -----------------------------
# CLI
# -----------------------------
def collect_targets(args: argparse.Namespace) -> List[str]:
    if args.scenario:
        return [args.scenario]
    targets: List[str] = []
    if args.scenario_folder:
        if args.recursive:
            for root, _, files in os.walk(args.scenario_folder):
                for fn in files:
                    if fn.lower().endswith(".json"):
                        targets.append(os.path.join(root, fn))
        else:
            for fn in os.listdir(args.scenario_folder):
                if fn.lower().endswith(".json"):
                    targets.append(os.path.join(args.scenario_folder, fn))
    return sorted(targets)


def main(argv: Optional[Iterable[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="EMVE Forward Spectrum Generator (psi/delta)")
    ap.add_argument("--scenario", type=str, help="Path to a single scenario JSON")
    ap.add_argument("--scenario-folder", type=str, help="Folder containing scenario JSONs")
    ap.add_argument("--material-dir", type=str, required=True, help="Folder containing material files")
    ap.add_argument("--outdir", type=str, required=True, help="Output folder")
    ap.add_argument("--recursive", action="store_true", help="Recurse into scenario-folder")
    args = ap.parse_args(argv)

    ensure_dir(args.outdir)
    targets = collect_targets(args)
    if not targets:
        raise SystemExit("Provide --scenario or --scenario-folder with JSON files")

    for p in targets:
        sc = load_json(p)
        out_csv = generate_spectrum(sc, args.material_dir, args.outdir)
        print(f"[OK] {sc['scenario_id']} -> {out_csv}")


if __name__ == "__main__":
    main()
