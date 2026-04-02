"""
AgriSignalMiner Tkinter (Context-first, Lexicon-first, Highlight + Explain) — Single file

FEATURES
- Mine agricultural innovation signals from a large Excel corpus
- CONTEXT-FIRST retrieval & extraction (NOT sentence-first)
- Lexicon-first slot filling + optional fuzzy matching (RapidFuzz) + semantic fallback
- Highlight extracted slots directly in the context text (Actor/Practice/Problem/Impact/Location)
- Explain WHY a row is Strong / Emerging / Weak / Noise with:
    - Final score + full score breakdown
    - Quantile thresholds (computed from the run’s score distribution)
    - Rule-like explanation bullets (what pushed the score up/down)

RUN
python agri_signal_miner_tk_context_highlight_explain.py

INSTALL
pip install pandas openpyxl numpy sentence-transformers faiss-cpu scikit-learn
(optional fuzzy)
pip install rapidfuzz
"""

import os
import re
import ast
import json
import time
import threading
import hashlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import faiss
from sklearn.cluster import KMeans
from sentence_transformers import SentenceTransformer, CrossEncoder

import matplotlib
matplotlib.use('TkAgg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# -------------------------
# OPTIONAL fuzzy (RapidFuzz)
# -------------------------
try:
    from rapidfuzz import fuzz
    RAPIDFUZZ_OK = True
except Exception:
    fuzz = None
    RAPIDFUZZ_OK = False


# =========================
# DEFAULT CONFIG
# =========================
DEFAULT_BI_ENCODER = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_USE_CROSS = False
DEFAULT_CROSS_ENCODER = "cross-encoder/ms-marco-MiniLM-L-6-v2"

DEFAULT_TOPK_RETRIEVE = 800
DEFAULT_TOPK_RERANK = 250

DEFAULT_APPLY_DEDUP = True
DEFAULT_DEDUP_COS_THRESHOLD = 0.92

DEFAULT_CLUSTER_SIGNALS = True
DEFAULT_N_CLUSTERS = 12

# Quantile-based strength thresholds
DEFAULT_Q_WEAK = 0.60
DEFAULT_Q_EMERGING = 0.80
DEFAULT_Q_STRONG = 0.93

DEFAULT_FUZZY_LEXICON = True
DEFAULT_FUZZY_THR = 88

DEFAULT_STORY_FILTER_ON = False
DEFAULT_STORY_PROB_THRESHOLD = 0.75
DEFAULT_STORY_PENALTY = 0.08

CACHE_DIR = "agri_cache_tk_ctx"
os.makedirs(CACHE_DIR, exist_ok=True)

CUSTOM_JSON = "agri_custom_config_tk_ctx.json"

EVIDENCE_REGEX = re.compile(
    r"(\d+(?:\.\d+)?\s*(?:%|kg|ha|tons?|tonnes?|USD|VND|days?|weeks?|months?))",
    re.I
)

# NOTE: Seeds can be multilingual; extraction & scoring will still work.
DEFAULT_INTENT_SEEDS = [
    "pilot", "experiment", "we tried", "we started using", "adopt", "switch to", "innovative approach",
    "trial", "test", "deploy", "implement",
    # Vietnamese examples (kept for robustness on VN corpus)
    "thử nghiệm", "thí điểm", "triển khai", "áp dụng", "bắt đầu sử dụng", "chuyển sang", "đổi sang"
]
DEFAULT_DIFFUSION_SEEDS = [
    "scaled up", "replicated", "many farmers adopted", "training program", "demonstration plot",
    "roll out", "expanded to", "widespread adoption",
    # Vietnamese examples (kept for robustness on VN corpus)
    "nhân rộng", "mở rộng", "lan rộng", "nhiều nông dân áp dụng", "tập huấn", "mô hình trình diễn"
]

DEFAULT_GAZETTEER = [
    "Mekong Delta", "Can Tho", "An Giang", "Dong Thap", "Ca Mau", "Kien Giang",
    "Soc Trang", "Bac Lieu", "Hau Giang", "Vinh Long", "Tien Giang", "Long An", "Tra Vinh", "Ben Tre",
    "Central Highlands", "Lam Dong", "Dak Lak", "Gia Lai",
    # Vietnamese spellings (kept for robustness)
    "ĐBSCL", "Mekong Delta", "Cần Thơ", "An Giang", "Đồng Tháp", "Cà Mau", "Kiên Giang",
    "Sóc Trăng", "Bạc Liêu", "Hậu Giang", "Vĩnh Long", "Tiền Giang", "Long An", "Trà Vinh", "Bến Tre",
    "Tây Nguyên", "Lâm Đồng", "Đắk Lắk", "Gia Lai"
]

DEFAULT_LEXICON = {
    "actor": [
        "farmer", "smallholder", "cooperative", "agribusiness", "extension worker",
        # Vietnamese (kept for robustness)
        "nông dân", "hộ nông dân", "hợp tác xã", "tổ hợp tác", "doanh nghiệp", "cán bộ khuyến nông",
    ],
    "practice": [
        "AWD", "drip irrigation", "integrated pest management",
        "biofertilizer", "organic farming", "sensor-based monitoring",
        "biofloc", "smart feeder", "IoT", "drone", "technologies",
        "alternate wetting and drying",
        # Vietnamese (kept for robustness)
        "tưới nhỏ giọt", "tưới tiết kiệm", "IPM", "canh tác hữu cơ", "phân bón sinh học",
        "tôm–lúa", "tôm lúa", "cảm biến mặn",
    ],
    "problem": [
        "drought", "salinity intrusion", "pest outbreak", "crop disease", "labor shortage",
        "high input costs", "price volatility", "soil degradation",
        # Vietnamese (kept for robustness)
        "hạn", "hạn hán", "xâm nhập mặn", "mặn", "dịch bệnh", "sâu bệnh", "thiếu lao động",
        "chi phí đầu vào cao", "giá cả biến động", "thoái hóa đất",
    ],
    "impact": [
        "increase yield", "reduce costs", "save water", "improve income", "reduce pesticide use",
        "improve quality", "higher profit",
        # Vietnamese (kept for robustness)
        "tăng năng suất", "tăng thu nhập", "giảm chi phí", "tiết kiệm nước", "giảm thuốc BVTV",
        "giảm phân hóa học", "tăng chất lượng", "tăng lợi nhuận", "ổn định thu nhập",
    ],
    "context": [
        "rice", "shrimp", "aquaculture", "Mekong Delta", "dry season", "rainy season",
        # Vietnamese (kept for robustness)
        "lúa", "tôm", "cá", "rau", "cây ăn trái", "ĐBSCL", "Mekong", "mùa khô", "mùa mưa",
    ],
}


DEFAULT_TEMPLATE_SPEC: Dict[str, Any] = {
    # How to join parts (e.g., " | ", " — ", "\n")
    "joiner": " | ",
    # Values to drop (case-insensitive) so templates stay compact
    "drop_values": ["", "unspecified", None],
    # Ordered fields to include in the template
    "fields": [
        {"key": "actor", "label": "Actor"},
        {"key": "practice_or_tech", "label": "Practice"},
        {"key": "location", "label": "Loc"},
        {"key": "problem", "label": "Problem"},
        {"key": "impact_or_evidence", "label": "Impact"},
    ],
    # If True: "Label: value" instead of raw values
    "show_labels": False,
}


# =========================
# Utilities
# =========================
def _norm(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, float) and pd.isna(x):
        return ""
    return str(x).strip()

def _safe_list(x: Any) -> List[str]:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return []
    if isinstance(x, list):
        return [str(i) for i in x]
    s = str(x).strip()
    if not s:
        return []
    try:
        v = ast.literal_eval(s)
        if isinstance(v, list):
            return [str(i) for i in v]
    except Exception:
        pass
    parts = re.split(r"[;,|\n]\s*", s)
    return [p for p in (p.strip() for p in parts) if p]

def _pick_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    lower_map = {c.lower(): c for c in df.columns}
    for k in candidates:
        if k.lower() in lower_map:
            return lower_map[k.lower()]
    return None

def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))

def _hash_text(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()

def _cache_path(tag: str, model_name: str, n: int, head_hash: str) -> str:
    return os.path.join(CACHE_DIR, f"{tag}__{_hash_text(model_name)}__{n}__{head_hash}.npy")

def _unique_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in items:
        x = str(x).strip()
        if not x:
            continue
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out

def _lower(s: str) -> str:
    return _norm(s).lower()

def _text_has_word(text_l: str, term_l: str) -> bool:
    if not term_l:
        return False
    if len(term_l) <= 3:
        return re.search(rf"\b{re.escape(term_l)}\b", text_l) is not None
    return term_l in text_l

def load_custom_config() -> Dict[str, Any]:
    if os.path.exists(CUSTOM_JSON):
        try:
            with open(CUSTOM_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_custom_config(cfg: Dict[str, Any]) -> None:
    with open(CUSTOM_JSON, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def build_dynamic_template(row: Dict[str, Any], spec: Optional[Dict[str, Any]]) -> str:
    """
    Build a human-readable template string from a row + a user-defined spec.

    spec example:
    {
      "joiner": " | ",
      "drop_values": ["", "unspecified", null],
      "fields": [{"key":"actor","label":"Actor"}, ...],
      "show_labels": false
    }
    """
    if not spec:
        spec = DEFAULT_TEMPLATE_SPEC

    joiner = spec.get("joiner", " | ")
    drop_values = spec.get("drop_values", ["", "unspecified", None])
    # normalize drop values to lower strings
    drop = set()
    for dv in drop_values:
        if dv is None:
            drop.add("")
            drop.add("none")
            drop.add("null")
        else:
            drop.add(str(dv).strip().lower())

    fields = spec.get("fields", [])
    show_labels = bool(spec.get("show_labels", False))

    parts: List[str] = []
    for f in fields:
        key = str(f.get("key", "")).strip()
        if not key:
            continue
        label = str(f.get("label", key)).strip()
        val = row.get(key, "")
        sval = "" if val is None else str(val).strip()
        if sval.strip().lower() in drop:
            continue
        parts.append(f"{label}: {sval}" if show_labels else sval)

    return joiner.join(parts) if parts else "unspecified"


# =========================
# Highlight helpers
# =========================
def _find_spans_in_text(text: str, phrase: str) -> List[Tuple[int, int]]:
    """Find all occurrences of a phrase in the text (case-insensitive)."""
    if not text or not phrase or phrase == "unspecified":
        return []
    p = phrase.strip()
    if not p:
        return []
    if len(p) <= 4:
        pattern = re.compile(rf"\b{re.escape(p)}\b", re.I)
    else:
        pattern = re.compile(re.escape(p), re.I)
    return [(m.start(), m.end()) for m in pattern.finditer(text)]

def _tk_index_from_charpos(pos: int) -> str:
    return f"1.0+{pos}c"


# =========================
# Embeddings + caching
# =========================
def embed_texts(model: SentenceTransformer, texts: List[str], batch_size: int = 96) -> np.ndarray:
    emb = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True
    )
    return emb.astype(np.float32)

def load_or_build_embeddings(tag: str, model: SentenceTransformer, model_name: str, texts: List[str], batch_size: int = 96) -> np.ndarray:
    head_hash = _hash_text("\n".join(texts[:800]))
    path = _cache_path(tag, model_name, len(texts), head_hash)
    if os.path.exists(path):
        return np.load(path)
    emb = embed_texts(model, texts, batch_size=batch_size)
    np.save(path, emb)
    return emb

def build_proto(model: SentenceTransformer, seeds: List[str]) -> np.ndarray:
    seeds = [s for s in seeds if _norm(s)]
    if not seeds:
        e = embed_texts(model, ["dummy"], batch_size=1)
        return e / (np.linalg.norm(e) + 1e-12)
    e = embed_texts(model, seeds, batch_size=64)
    proto = np.mean(e, axis=0, keepdims=True)
    proto = proto / (np.linalg.norm(proto) + 1e-12)
    return proto.astype(np.float32)

def build_protos(model: SentenceTransformer, lexicon: Dict[str, List[str]]) -> Dict[str, np.ndarray]:
    protos = {}
    for slot in ["actor", "practice", "problem", "impact", "context"]:
        protos[slot] = build_proto(model, lexicon.get(slot, []))
    protos["intent"] = build_proto(model, DEFAULT_INTENT_SEEDS)
    protos["diffusion"] = build_proto(model, DEFAULT_DIFFUSION_SEEDS)
    return protos


# =========================
# FAISS retrieval
# =========================
def build_faiss_index(emb: np.ndarray) -> faiss.Index:
    dim = emb.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(emb)
    return index

def faiss_search(index: faiss.Index, q_emb: np.ndarray, topk: int) -> Tuple[np.ndarray, np.ndarray]:
    scores, idx = index.search(q_emb.astype(np.float32), topk)
    return scores[0], idx[0]

def rerank(cross: CrossEncoder, query: str, candidates: List[str], batch_size: int = 32) -> np.ndarray:
    pairs = [(query, c) for c in candidates]
    s = cross.predict(pairs, batch_size=batch_size)
    s = (s - np.min(s)) / (np.ptp(s) + 1e-12)
    return s.astype(np.float32)

def make_query_global() -> str:
    return "agricultural innovation signals: new practices/technologies adopted in farming to address problems and improve outcomes"


# =========================
# Lexicon matching (context-first)
# =========================
def lexicon_match(context: str, terms: List[str], fuzzy: bool = True, fuzzy_thr: int = 88, max_hits: int = 8) -> List[str]:
    t = _lower(context)
    hits = []
    for term in terms:
        tl = term.lower().strip()
        if tl and _text_has_word(t, tl):
            hits.append(term)
    hits = _unique_keep_order(hits)
    if hits:
        return hits[:max_hits]

    if fuzzy and RAPIDFUZZ_OK and terms and _norm(context):
        segs = re.split(r"[.\n;:•\-]+", context)
        segs = [s.strip() for s in segs if len(s.strip()) >= 10]
        segs = segs[:50]
        best = []
        for term in terms:
            tl = term.lower().strip()
            if not tl:
                continue
            best_score = 0
            for seg in segs:
                sc = fuzz.partial_ratio(tl, seg.lower())
                if sc > best_score:
                    best_score = sc
            if best_score >= fuzzy_thr:
                best.append((term, best_score))
        best.sort(key=lambda x: (-x[1], -len(x[0])))
        return [b[0] for b in best[:max_hits]]
    return []


# =========================
# Semantic fallback slot fill (context candidates)
# =========================
def extract_candidate_phrases_context(context: str, cap: int = 140) -> List[str]:
    t = _norm(context)
    if not t:
        return []
    segs = re.split(r"[.\n;:(){}\[\]\|]+", t)
    segs = [s.strip() for s in segs if 8 <= len(s.strip()) <= 350]
    segs = segs[:60]
    cands = []
    for seg in segs:
        words = re.findall(r"[\w\-À-ỹ]+", seg)
        if not words:
            continue
        for n in range(1, 6):
            for i in range(0, max(0, len(words) - n + 1)):
                ph = " ".join(words[i:i+n]).strip()
                if 4 <= len(ph) <= 60:
                    cands.append(ph)
    cands = _unique_keep_order(cands)
    return cands[:cap]

def best_phrase_by_semantic_verify(bi: SentenceTransformer, phrases: List[str], proto: np.ndarray) -> Tuple[str, float]:
    if not phrases:
        return "unspecified", 0.0
    ph_emb = embed_texts(bi, phrases, batch_size=min(256, max(8, len(phrases))))
    sims = (ph_emb @ proto.T).reshape(-1)
    j = int(np.argmax(sims))
    return phrases[j], float(sims[j])


# =========================
# Geo extraction (context-first)
# =========================
def extract_location_from_context(context: str, gazetteer: List[str]) -> str:
    t = _lower(context)
    hits = []
    for g in gazetteer:
        gl = g.lower().strip()
        if gl and _text_has_word(t, gl):
            hits.append(g)
    hits = _unique_keep_order(hits)
    return "; ".join(hits) if hits else "unspecified"


# =========================
# Scoring
# =========================
def sem_map(sim: float, lo: float = 0.28, hi: float = 0.60) -> float:
    return _clip01((sim - lo) / (hi - lo))

def evidence_score(text: str) -> float:
    if EVIDENCE_REGEX.search(text):
        return 1.0
    markers = [
        "increase", "improve", "reduce", "save", "profit", "yield", "income", "efficiency", "quality",
        # Vietnamese markers (kept for robustness)
        "tăng", "giảm", "tiết kiệm", "nâng", "hiệu quả", "năng suất", "thu nhập", "lợi nhuận"
    ]
    k = sum(1 for m in markers if m in text.lower())
    return _clip01(0.2 + 0.12 * min(k, 6))

def proto_score(bi: SentenceTransformer, text: str, proto: np.ndarray, lo=0.22, hi=0.54) -> float:
    if not _norm(text):
        return 0.0
    e = embed_texts(bi, [text], batch_size=1)
    sim = float((e @ proto.T)[0, 0])
    return sem_map(sim, lo=lo, hi=hi)

def structural_score(slot_sims: List[float]) -> float:
    confident = sum(1 for s in slot_sims if s >= 0.45)
    return confident / 4.0

def deviation_score(practice_text: str, practice_sim: float) -> float:
    t = practice_text.lower()
    cues = [
        "switch", "replace", "instead", "diversif", "organic", "reduce", "smart", "precision",
        "awd", "ipm", "bio", "sensor", "ai", "drip", "biofloc", "smart feeder",
        # Vietnamese cues (kept for robustness)
        "tôm", "lúa", "tưới", "canh tác", "cảm biến", "truy xuất", "qr"
    ]
    k = sum(1 for c in cues if c in t)
    return _clip01(0.35 * sem_map(practice_sim) + 0.65 * (0.10 + 0.12 * min(k, 6)))

def problem_solution_score(prob_sim: float, imp_sim: float) -> float:
    return _clip01(0.55 * sem_map(prob_sim) + 0.45 * sem_map(imp_sim))

def geo_score(loc: str) -> float:
    return 1.0 if loc != "unspecified" else 0.0

def final_score(sem_rel, struct, dev, intent, ps, evid, diff, geo):
    base = (
        0.28 * sem_rel +
        0.12 * struct +
        0.16 * dev +
        0.14 * intent +
        0.12 * ps +
        0.08 * evid +
        0.06 * diff +
        0.04 * geo
    )
    # Penalty: lacks adoption intent AND lacks problem->impact coherence
    if intent < 0.25 and ps < 0.35:
        base *= 0.65
    return float(_clip01(base))

def quantile_thresholds(scores: np.ndarray, q_weak=0.60, q_emerging=0.80, q_strong=0.93) -> Tuple[float, float, float]:
    s = scores.copy()
    t1 = float(np.quantile(s, q_weak))
    t2 = float(np.quantile(s, q_emerging))
    t3 = float(np.quantile(s, q_strong))
    return t1, t2, t3

def label_by_threshold(score: float, t1: float, t2: float, t3: float) -> str:
    if score >= t3:
        return "strong"
    if score >= t2:
        return "emerging"
    if score >= t1:
        return "weak"
    return "noise"

def dedup_by_cosine(emb: np.ndarray, scores: np.ndarray, threshold: float = 0.92) -> List[int]:
    order = np.argsort(-scores)
    kept = []
    for idx in order:
        if not kept:
            kept.append(int(idx))
            continue
        sims = (emb[idx:idx+1] @ emb[np.array(kept)].T).reshape(-1)
        if float(np.max(sims)) < threshold:
            kept.append(int(idx))
    return kept


# =========================
# Explanation (why strong/emerging/weak)
# =========================
def build_strength_explanation(r: pd.Series, thr: Dict[str, float], q: Dict[str, float]) -> str:
    """
    Explains:
    - label assignment rule based on quantile thresholds
    - final score vs thresholds
    - score breakdown with weights
    - bullet reasons + weaknesses
    """
    score = float(r.get("final_signal_score", 0.0))
    t1, t2, t3 = thr["t_weak"], thr["t_emerging"], thr["t_strong"]
    label = str(r.get("signal_strength", ""))
    parts: List[str] = []

    parts.append("HOW THE SIGNAL STRENGTH IS DECIDED (quantile-based):")
    parts.append("- We compute thresholds from the distribution of final_score over the whole run:")
    parts.append(f"  • q_weak={q['q_weak']:.2f}  ⇒  t_weak={t1:.3f}")
    parts.append(f"  • q_emerging={q['q_emerging']:.2f}  ⇒  t_emerging={t2:.3f}")
    parts.append(f"  • q_strong={q['q_strong']:.2f}  ⇒  t_strong={t3:.3f}")
    parts.append("- Labeling rule:")
    parts.append("  • strong   if score ≥ t_strong")
    parts.append("  • emerging if t_emerging ≤ score < t_strong")
    parts.append("  • weak     if t_weak ≤ score < t_emerging")
    parts.append("  • noise    if score < t_weak")
    parts.append("")
    parts.append("DECISION FOR THIS ROW:")
    parts.append(f"- final_score = {score:.3f}  ⇒  label = {label.upper()}")

    sem_rel = float(r.get("semantic_relevance", 0.0))
    struct = float(r.get("structural_score", 0.0))
    dev = float(r.get("deviation_score", 0.0))
    intent = float(r.get("intent_score", 0.0))
    ps = float(r.get("problem_solution_score", 0.0))
    evid = float(r.get("evidence_score", 0.0))
    diff = float(r.get("diffusion_score", 0.0))
    geo = float(r.get("geo_score", 0.0))

    parts.append("")
    parts.append("COMPONENT SCORES (contribution to final_score):")
    parts.append(f"- semantic_relevance (w=0.28): {sem_rel:.2f}  → contrib {0.28*sem_rel:.3f}")
    parts.append(f"- structural_score  (w=0.12): {struct:.2f}  → contrib {0.12*struct:.3f}")
    parts.append(f"- deviation_score   (w=0.16): {dev:.2f}  → contrib {0.16*dev:.3f}")
    parts.append(f"- intent_score      (w=0.14): {intent:.2f}  → contrib {0.14*intent:.3f}")
    parts.append(f"- problem→impact    (w=0.12): {ps:.2f}  → contrib {0.12*ps:.3f}")
    parts.append(f"- evidence_score    (w=0.08): {evid:.2f}  → contrib {0.08*evid:.3f}")
    parts.append(f"- diffusion_score   (w=0.06): {diff:.2f}  → contrib {0.06*diff:.3f}")
    parts.append(f"- geo_score         (w=0.04): {geo:.2f}  → contrib {0.04*geo:.3f}")

    reasons: List[str] = []
    weaknesses: List[str] = []

    if sem_rel >= 0.70:
        reasons.append("High semantic relevance (semantic_relevance ≥ 0.70).")
    else:
        weaknesses.append("Semantic relevance is not very high (semantic_relevance < 0.70).")

    if struct >= 0.75:
        reasons.append("Well-formed template with confident slots (structural_score ≥ 0.75).")
    else:
        weaknesses.append("Template is incomplete / slot confidence is limited (structural_score < 0.75).")

    if ps >= 0.60:
        reasons.append("Clear problem→impact coherence (problem_solution_score ≥ 0.60).")
    else:
        weaknesses.append("Problem→impact link is weak (problem_solution_score < 0.60).")

    if evid >= 0.90:
        reasons.append("Strong quantitative evidence present (evidence_score ≥ 0.90).")
    elif evid >= 0.55:
        reasons.append("Some benefit/efficiency markers present (evidence_score is moderate).")
    else:
        weaknesses.append("Little quantitative evidence or benefit markers (evidence_score is low).")

    if intent >= 0.60:
        reasons.append("Clear adoption/pilot intent markers (intent_score ≥ 0.60).")
    else:
        weaknesses.append("Adoption/pilot intent markers are weak (intent_score is low).")

    if diff >= 0.60:
        reasons.append("Diffusion/scale-out signals present (diffusion_score ≥ 0.60).")
    else:
        weaknesses.append("Diffusion/scale-out is not clearly mentioned (diffusion_score is low).")

    if geo >= 0.90:
        reasons.append("Specific location is identified (geo_score=1).")
    else:
        weaknesses.append("No specific location found (geo_score=0).")

    parts.append("")
    parts.append("WHY THIS COUNTS AS A SIGNAL (rule-like):")
    if reasons:
        for x in reasons:
            parts.append(f"- {x}")
    else:
        parts.append("- Not enough strong indicators; may need clearer structure and/or stronger markers.")

    parts.append("")
    parts.append("WHAT PULLS THE SCORE DOWN (if any):")
    if weaknesses:
        for x in weaknesses:
            parts.append(f"- {x}")
    else:
        parts.append("- No major weaknesses under the current thresholds.")

    if intent < 0.25 and ps < 0.35:
        parts.append("")
        parts.append("NOTE: A penalty was applied because intent_score < 0.25 AND problem_solution_score < 0.35 (final_score ×= 0.65).")

    return "\n".join(parts)


# =========================
# Column detection
# =========================
@dataclass
class ColumnMap:
    context: str
    sentence: Optional[str]
    labels: Optional[str]
    source: Optional[str]
    date: Optional[str]

def detect_columns(df: pd.DataFrame) -> ColumnMap:
    col_context = _pick_col(df, ["Content", "context", "document_text", "Doc", "Document", "Context Text", "context_text"])
    if col_context is None:
        raise ValueError(
            "Cannot find a CONTEXT column. Expected one of: "
            "Content / context / document_text / Doc / Document / context_text"
        )
    col_sentence = _pick_col(df, ["Sentence Text", "sentence", "text", "Sentence", "chunk"])
    col_labels   = _pick_col(df, ["Labels List", "labels", "gliner_labels", "Entities", "NER"])
    col_source   = _pick_col(df, ["Source", "method", "branch", "file"])
    
    col_date    = _pick_col(df, ["date", "Date", "timestamp", "Timestamp", "time", "Time", "created_at", "Created", "created", "createdAt", "year", "Year", "month", "Month"])
    return ColumnMap(context=col_context, sentence=col_sentence, labels=col_labels, source=col_source, date=col_date)



# =========================
# Story vs Innovation (heuristics)
# =========================
def story_innovation_scores(text: str) -> Tuple[float, float, float]:
    """
    Heuristic detector for narrative (story) vs innovation signals.
    Returns: (story_score, innov_marker_score, story_prob in [0,1]).
    - story_score: higher when text is personal narrative (pronouns, daily life, income, family, emotion).
    - innov_marker_score: higher when text contains adoption/implementation/tech/practice markers.
    """
    t = _lower(text)

    story_markers = [
        "i ", "we ", "he ", "she ", "they ", "my ", "his ", "her ",
        "family", "children", "school", "daily", "per day", "income", "expenses",
        "borrow", "debt", "money", "hard", "fear", "hope",
        # Vietnamese
        "tôi", "chúng tôi", "anh", "chị", "gia đình", "con", "trường", "chi tiêu",
        "thu nhập", "vay", "nợ", "tiền", "khó", "sợ", "hy vọng"
    ]
    innov_markers = DEFAULT_INTENT_SEEDS + DEFAULT_DIFFUSION_SEEDS + [
        "introduced", "new technique", "new practice", "technology", "mechanization", "machine planting",
        "canal", "irrigation", "drip", "biofertilizer", "sensor", "iot", "drone", "ai",
        # Vietnamese
        "kỹ thuật", "công nghệ", "cơ giới", "máy", "kênh", "mương", "tưới", "cảm biến", "iot", "drone", "ai"
    ]

    s_cnt = sum(1 for m in story_markers if m and m in t)
    i_cnt = sum(1 for m in innov_markers if m and m.lower() in t)

    story_score = _clip01(0.15 + 0.12 * min(s_cnt, 8))
    innov_score = _clip01(0.10 + 0.12 * min(i_cnt, 8))

    # story_prob increases when story markers dominate innovation markers
    story_prob = _clip01(0.50 + 0.40 * (story_score - innov_score))
    return float(story_score), float(innov_score), float(story_prob)


# =========================
# Mining core (context-first)
# =========================
def run_mining_context_first(
    input_xlsx: str,
    bi_encoder: str,
    use_cross: bool,
    cross_encoder: str,
    topk_retrieve: int,
    topk_rerank: int,
    apply_dedup: bool,
    dedup_thr: float,
    cluster_signals: bool,
    n_clusters: int,
    q_weak: float,
    q_emerging: float,
    q_strong: float,
    fuzzy_lexicon: bool,
    fuzzy_thr: int,
    lexicon: Dict[str, List[str]],
    gazetteer: List[str],
    template_spec: Optional[Dict[str, Any]] = None,
    extra_config: Optional[Dict[str, Any]] = None,
    progress_cb=None
):
    t0 = time.time()
    df = pd.read_excel(input_xlsx)
    cmap = detect_columns(df)

    contexts = [_norm(x) for x in df[cmap.context].tolist()]
    sentences = [_norm(df[cmap.sentence].iloc[i]) if cmap.sentence else "" for i in range(len(df))]
    labels_ls = [_safe_list(df[cmap.labels].iloc[i]) if cmap.labels else [] for i in range(len(df))]
    src_ls = [_norm(df[cmap.source].iloc[i]) if cmap.source else "" for i in range(len(df))]
    dates_ls = [df[cmap.date].iloc[i] if getattr(cmap, 'date', None) else None for i in range(len(df))]

    if progress_cb: progress_cb(0.05, "Loading models...")
    bi = SentenceTransformer(bi_encoder)
    cross = CrossEncoder(cross_encoder) if use_cross else None

    if progress_cb: progress_cb(0.12, "Building prototypes...")
    protos = build_protos(bi, lexicon)

    if progress_cb: progress_cb(0.20, "Embedding CONTEXT + building FAISS...")
    ctx_emb = load_or_build_embeddings("ctx", bi, bi_encoder, contexts, batch_size=96)
    index = build_faiss_index(ctx_emb)

    query = make_query_global()
    q_emb = embed_texts(bi, [query], batch_size=1)

    if progress_cb: progress_cb(0.28, "Retrieving candidates (context-index)...")
    faiss_scores, faiss_idx = faiss_search(index, q_emb, topk_retrieve)
    cand_ctx = [contexts[i] for i in faiss_idx]

    if cross is not None:
        if progress_cb: progress_cb(0.34, "Reranking (cross-encoder)...")
        ce = rerank(cross, query, cand_ctx, batch_size=32)
        order = np.argsort(-ce)[:topk_rerank]
    else:
        ce = None
        order = np.argsort(-faiss_scores)[:topk_rerank]

    sel_idx = faiss_idx[order]
    sel_faiss = faiss_scores[order]
    sel_ce = ce[order] if ce is not None else None

    rows = []
    total = len(sel_idx)

    for k, ridx in enumerate(sel_idx):
        if progress_cb:
            progress_cb(0.38 + 0.48*(k/max(1,total)), f"Extracting from CONTEXT ({k+1}/{total})...")

        ctx = contexts[ridx]
        sent = sentences[ridx]  # display only
        lbls = labels_ls[ridx]
        src = src_ls[ridx]

        # Semantic relevance from retrieval score (+ optional cross-encoder)
        sem_rel = sem_map(float(sel_faiss[k]), lo=0.18, hi=0.58)
        if sel_ce is not None:
            sem_rel = float(_clip01(0.45*sem_rel + 0.55*float(sel_ce[k])))

        loc = extract_location_from_context(ctx, gazetteer)

        # Lexicon hits (context-first)
        actor_hits = lexicon_match(ctx, lexicon.get("actor", []), fuzzy=fuzzy_lexicon, fuzzy_thr=fuzzy_thr, max_hits=6)
        prac_hits  = lexicon_match(ctx, lexicon.get("practice", []), fuzzy=fuzzy_lexicon, fuzzy_thr=fuzzy_thr, max_hits=6)
        prob_hits  = lexicon_match(ctx, lexicon.get("problem", []), fuzzy=fuzzy_lexicon, fuzzy_thr=fuzzy_thr, max_hits=6)
        imp_hits   = lexicon_match(ctx, lexicon.get("impact", []), fuzzy=fuzzy_lexicon, fuzzy_thr=fuzzy_thr, max_hits=6)
        ctx_hits   = lexicon_match(ctx, lexicon.get("context", []), fuzzy=fuzzy_lexicon, fuzzy_thr=fuzzy_thr, max_hits=6)

        def pick_best(hits: List[str]) -> Optional[str]:
            if not hits:
                return None
            hits2 = sorted(hits, key=lambda x: (-len(x), x))
            return hits2[0]

        actor    = pick_best(actor_hits)
        practice = pick_best(prac_hits)
        problem  = pick_best(prob_hits)
        impact   = pick_best(imp_hits)
        context_tag = pick_best(ctx_hits)

        # If lexicon hit exists, assign a high "slot sim" proxy confidence
        actor_sim = 0.80 if actor else 0.0
        practice_sim = 0.84 if practice else 0.0
        problem_sim = 0.80 if problem else 0.0
        impact_sim = 0.80 if impact else 0.0
        context_sim = 0.72 if context_tag else 0.0

        # Semantic fallback when lexicon misses
        candidates = extract_candidate_phrases_context(ctx, cap=140)

        if not actor:
            actor, actor_sim = best_phrase_by_semantic_verify(bi, candidates, protos["actor"])
        if not practice:
            practice, practice_sim = best_phrase_by_semantic_verify(bi, candidates, protos["practice"])
        if not problem:
            problem, problem_sim = best_phrase_by_semantic_verify(bi, candidates, protos["problem"])
        if not impact:
            impact, impact_sim = best_phrase_by_semantic_verify(bi, candidates, protos["impact"])
        if not context_tag:
            context_tag, context_sim = best_phrase_by_semantic_verify(bi, candidates, protos["context"])

        # Low confidence → unspecified
        if actor_sim < 0.35: actor = "unspecified"
        if practice_sim < 0.35: practice = "unspecified"
        if problem_sim < 0.35: problem = "unspecified"
        if impact_sim < 0.35: impact = "unspecified"
        if context_sim < 0.35: context_tag = "unspecified"

        struct = structural_score([actor_sim, practice_sim, problem_sim, impact_sim])
        dev = deviation_score(practice, practice_sim)
        intent = proto_score(bi, ctx, protos["intent"], lo=0.22, hi=0.54)
        diff = proto_score(bi, ctx, protos["diffusion"], lo=0.22, hi=0.54)
        ps = problem_solution_score(problem_sim, impact_sim)
        evid = evidence_score(ctx)
        g = geo_score(loc)
        story_s, innov_s, story_prob = story_innovation_scores(ctx)

        fscore = final_score(sem_rel, struct, dev, intent, ps, evid, diff, g)
        tpl_row = {
            "actor": actor,
            "practice_or_tech": practice,
            "location": loc,
            "problem": problem,
            "impact_or_evidence": impact,
            "context_tag": context_tag,
        }
        template = build_dynamic_template(tpl_row, template_spec)

        rows.append({
            "date": dates_ls[ridx] if cmap.date else None,
            "source": src,
            "sentence_display": sent,
            "context_text": ctx[:12000],
            "labels_raw": "; ".join(lbls),

            "location": loc,
            "actor": actor, "actor_sim": float(actor_sim),
            "practice_or_tech": practice, "practice_sim": float(practice_sim),
            "problem": problem, "problem_sim": float(problem_sim),
            "impact_or_evidence": impact, "impact_sim": float(impact_sim),
            "context_tag": context_tag, "context_sim": float(context_sim),

            "lex_actor_hits": "; ".join(actor_hits),
            "lex_practice_hits": "; ".join(prac_hits),
            "lex_problem_hits": "; ".join(prob_hits),
            "lex_impact_hits": "; ".join(imp_hits),

            "faiss_score": float(sel_faiss[k]),
            "cross_encoder_score": float(sel_ce[k]) if sel_ce is not None else None,
            "semantic_relevance": float(sem_rel),
            "story_score": float(story_s),
            "innov_marker_score": float(innov_s),
            "story_prob": float(story_prob),

            "structural_score": float(struct),
            "deviation_score": float(dev),
            "intent_score": float(intent),
            "problem_solution_score": float(ps),
            "evidence_score": float(evid),
            "diffusion_score": float(diff),
            "geo_score": float(g),

            "final_signal_score": float(fscore),
            "signal_template": template,
            "practice_at_location": f"{practice} @ {loc}" if loc != "unspecified" else practice,
        })

    out_df = pd.DataFrame(rows).sort_values("final_signal_score", ascending=False).reset_index(drop=True)
    # Apply optional narrative filter / penalty (controlled by UI config)
    story_filter_on = bool((extra_config or {}).get("story_filter_on", False))
    story_thr = float((extra_config or {}).get("story_prob_threshold", 0.75))
    story_penalty = float((extra_config or {}).get("story_penalty", 0.08))  # subtract story_prob * penalty

    if len(out_df) > 0:
        out_df["final_signal_score_raw"] = out_df["final_signal_score"]
        if story_filter_on:
            out_df["final_signal_score"] = np.maximum(
                0.0, out_df["final_signal_score_raw"] - out_df["story_prob"] * story_penalty
            )
            out_df = out_df[~((out_df["story_prob"] >= story_thr) & (out_df["innov_marker_score"] <= 0.0))].copy()
        else:
            out_df["final_signal_score"] = out_df["final_signal_score_raw"]





    if len(out_df) == 0:
        return out_df, pd.DataFrame(), pd.DataFrame(), {"t_weak": 0, "t_emerging": 0, "t_strong": 0}

    if progress_cb: progress_cb(0.88, "Post-processing (dedup / thresholds / clustering / hotspots)...")

    # Embeddings for dedup/clustering
    bi2 = SentenceTransformer(bi_encoder)  # lightweight reuse
    tmpl_emb = embed_texts(bi2, out_df["signal_template"].tolist(), batch_size=96)
    scores = out_df["final_signal_score"].values.astype(np.float32)

    # Dedup (optional)
    if apply_dedup and len(out_df) > 0:
        keep = dedup_by_cosine(tmpl_emb, scores, threshold=dedup_thr)
        out_df = out_df.iloc[keep].sort_values("final_signal_score", ascending=False).reset_index(drop=True)
        tmpl_emb = tmpl_emb[keep]
        scores = out_df["final_signal_score"].values.astype(np.float32)

    # Compute thresholds (quantiles) and label
    t1, t2, t3 = quantile_thresholds(scores, q_weak=q_weak, q_emerging=q_emerging, q_strong=q_strong)
    thr = {"t_weak": t1, "t_emerging": t2, "t_strong": t3}
    out_df["signal_strength"] = [label_by_threshold(float(s), t1, t2, t3) for s in scores]

    # Clustering (optional)
    if cluster_signals and len(out_df) >= max(3, n_clusters):
        km = KMeans(n_clusters=n_clusters, random_state=42, n_init="auto")
        out_df["cluster_id"] = km.fit_predict(tmpl_emb)
    else:
        out_df["cluster_id"] = -1

    # Hotspots (only emerging/strong)
    focus = out_df[out_df["signal_strength"].isin(["emerging", "strong"])].copy()
    if len(focus) > 0:
        hotspots = (focus.groupby(["location", "practice_or_tech"])
                         .size().reset_index(name="count")
                         .sort_values("count", ascending=False))
    else:
        hotspots = pd.DataFrame(columns=["location", "practice_or_tech", "count"])

    topic_summary = (out_df.groupby(["cluster_id", "signal_strength"])
                          .size().reset_index(name="count")
                          .sort_values(["cluster_id", "count"], ascending=[True, False]))

    if progress_cb: progress_cb(1.0, f"Done in {time.time()-t0:.1f}s")

    return out_df, hotspots, topic_summary, thr


# =========================
# Tkinter GUI
# =========================
class AgriSignalMinerGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("AgriSignalMiner — Context-first + Highlight + Explain (Tkinter)")
        self.root.geometry("1460x900")

        self.input_path = tk.StringVar(value="")
        self.output_path = tk.StringVar(value=os.path.abspath("agri_signals_export.xlsx"))

        # Settings
        self.bi_encoder = tk.StringVar(value=DEFAULT_BI_ENCODER)
        self.use_cross = tk.BooleanVar(value=DEFAULT_USE_CROSS)
        self.cross_encoder = tk.StringVar(value=DEFAULT_CROSS_ENCODER)

        self.topk_retrieve = tk.IntVar(value=DEFAULT_TOPK_RETRIEVE)
        self.topk_rerank = tk.IntVar(value=DEFAULT_TOPK_RERANK)

        self.apply_dedup = tk.BooleanVar(value=DEFAULT_APPLY_DEDUP)
        self.dedup_thr = tk.DoubleVar(value=DEFAULT_DEDUP_COS_THRESHOLD)

        self.cluster_signals = tk.BooleanVar(value=DEFAULT_CLUSTER_SIGNALS)
        self.n_clusters = tk.IntVar(value=DEFAULT_N_CLUSTERS)

        self.q_weak = tk.DoubleVar(value=DEFAULT_Q_WEAK)
        self.q_emerging = tk.DoubleVar(value=DEFAULT_Q_EMERGING)
        self.q_strong = tk.DoubleVar(value=DEFAULT_Q_STRONG)

        self.fuzzy_lexicon = tk.BooleanVar(value=DEFAULT_FUZZY_LEXICON)
        self.fuzzy_thr = tk.IntVar(value=DEFAULT_FUZZY_THR)

        # Narrative (story) filter
        self.story_filter_on = tk.BooleanVar(value=DEFAULT_STORY_FILTER_ON)
        self.story_prob_threshold = tk.DoubleVar(value=DEFAULT_STORY_PROB_THRESHOLD)
        self.story_penalty = tk.DoubleVar(value=DEFAULT_STORY_PENALTY)

        # Data
        self.df_full: Optional[pd.DataFrame] = None
        self.df_hotspots: Optional[pd.DataFrame] = None
        self.df_topic: Optional[pd.DataFrame] = None
        self._table_view_df: Optional[pd.DataFrame] = None
        self.thresholds: Dict[str, float] = {"t_weak": 0.0, "t_emerging": 0.0, "t_strong": 0.0}

        # Progress
        self.progress = tk.DoubleVar(value=0.0)
        self.status = tk.StringVar(value="Ready.")

        # Custom config
        cfg = load_custom_config()
        self.custom_gazetteer = _unique_keep_order(cfg.get("gazetteer", DEFAULT_GAZETTEER))
        self.custom_lexicon = cfg.get("lexicon", DEFAULT_LEXICON)
        self.custom_lexicon = {k: _unique_keep_order(list(self.custom_lexicon.get(k, [])))
                               for k in ["actor","practice","problem","impact","context"]}

        self.custom_template_spec = cfg.get("template_spec", DEFAULT_TEMPLATE_SPEC)

        self._build_ui()

    # ---------- UI ----------
    # ---------- file handlers (defined early to avoid AttributeError if file is partially edited) ----------
    def on_browse_input(self):
        path = filedialog.askopenfilename(title="Select input Excel", filetypes=[("Excel files", "*.xlsx *.xls")])
        if path:
            self.input_path.set(path)

    def on_browse_output(self):
        path = filedialog.asksaveasfilename(
            title="Save output Excel as",
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx")]
        )
        if path:
            self.output_path.set(path)

    def _build_ui(self):
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill="x")

        ttk.Label(top, text="Input Excel:").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.input_path, width=105).grid(row=0, column=1, padx=6, sticky="we")
        ttk.Button(top, text="Browse", command=self.on_browse_input).grid(row=0, column=2, padx=4)

        ttk.Label(top, text="Output Excel:").grid(row=1, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.output_path, width=105).grid(row=1, column=1, padx=6, sticky="we")
        ttk.Button(top, text="Browse", command=self.on_browse_output).grid(row=1, column=2, padx=4)

        ttk.Button(top, text="Run Mining", command=self.on_run).grid(row=0, column=3, padx=10, rowspan=2, sticky="ns")
        ttk.Button(top, text="Export Results", command=self.on_export).grid(row=0, column=4, padx=4, rowspan=2, sticky="ns")

        top.columnconfigure(1, weight=1)

        bar = ttk.Frame(self.root, padding=(8,0,8,8))
        bar.pack(fill="x")
        ttk.Progressbar(bar, variable=self.progress, maximum=1.0).pack(fill="x")
        ttk.Label(bar, textvariable=self.status).pack(anchor="w", pady=(4,0))

        main = ttk.Panedwindow(self.root, orient="horizontal")
        main.pack(fill="both", expand=True, padx=8, pady=8)

        left = ttk.Frame(main, padding=8)
        main.add(left, weight=1)
        self._build_settings(left)

        right = ttk.Frame(main, padding=8)
        main.add(right, weight=4)

        nb = ttk.Notebook(right)
        nb.pack(fill="both", expand=True)

        tab_signals = ttk.Frame(nb)
        nb.add(tab_signals, text="Signals")
        self._build_signals_tab(tab_signals)

        tab_hot = ttk.Frame(nb)
        nb.add(tab_hot, text="Hotspots")
        self._build_hotspots_tab(tab_hot)

        tab_topic = ttk.Frame(nb)
        nb.add(tab_topic, text="Topic Summary")
        self._build_topic_tab(tab_topic)

        tab_timeline = ttk.Frame(nb)
        nb.add(tab_timeline, text="Timeline")
        self._build_timeline_tab(tab_timeline)

        tab_custom = ttk.Frame(nb)
        nb.add(tab_custom, text="Customize (Gazetteer + Lexicon)")
        self._build_customize_tab(tab_custom)

    def _build_settings(self, parent):
        ttk.Label(parent, text="Settings", font=("Arial", 12, "bold")).pack(anchor="w", pady=(0,8))

        frm = ttk.LabelFrame(parent, text="Models", padding=8)
        frm.pack(fill="x", pady=6)

        ttk.Label(frm, text="Bi-encoder:").grid(row=0, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.bi_encoder, width=42).grid(row=0, column=1, sticky="we", padx=6)

        ttk.Checkbutton(frm, text="Use Cross-Encoder (optional)", variable=self.use_cross).grid(row=1, column=0, sticky="w", pady=2)
        ttk.Entry(frm, textvariable=self.cross_encoder, width=42).grid(row=1, column=1, sticky="we", padx=6)

        frm.columnconfigure(1, weight=1)

        frm2 = ttk.LabelFrame(parent, text="Retrieval", padding=8)
        frm2.pack(fill="x", pady=6)
        ttk.Label(frm2, text="TOPK retrieve:").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(frm2, from_=50, to=20000, textvariable=self.topk_retrieve, width=10).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(frm2, text="TOPK rerank:").grid(row=1, column=0, sticky="w")
        ttk.Spinbox(frm2, from_=20, to=8000, textvariable=self.topk_rerank, width=10).grid(row=1, column=1, sticky="w", padx=6)

        frm3 = ttk.LabelFrame(parent, text="Dedup / Clustering", padding=8)
        frm3.pack(fill="x", pady=6)

        ttk.Checkbutton(frm3, text="Dedup", variable=self.apply_dedup).grid(row=0, column=0, sticky="w")
        ttk.Label(frm3, text="Dedup thr:").grid(row=0, column=1, sticky="w")
        ttk.Spinbox(frm3, from_=0.80, to=0.99, increment=0.01, textvariable=self.dedup_thr, width=6).grid(row=0, column=2, sticky="w")

        ttk.Checkbutton(frm3, text="Cluster signals", variable=self.cluster_signals).grid(row=1, column=0, sticky="w")
        ttk.Label(frm3, text="#Clusters:").grid(row=1, column=1, sticky="w")
        ttk.Spinbox(frm3, from_=3, to=60, textvariable=self.n_clusters, width=6).grid(row=1, column=2, sticky="w")

        frm4 = ttk.LabelFrame(parent, text="Calibration (quantiles)", padding=8)
        frm4.pack(fill="x", pady=6)
        ttk.Label(frm4, text="q_weak:").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(frm4, from_=0.1, to=0.9, increment=0.01, textvariable=self.q_weak, width=6).grid(row=0, column=1, sticky="w")
        ttk.Label(frm4, text="q_emerging:").grid(row=1, column=0, sticky="w")
        ttk.Spinbox(frm4, from_=0.1, to=0.99, increment=0.01, textvariable=self.q_emerging, width=6).grid(row=1, column=1, sticky="w")
        ttk.Label(frm4, text="q_strong:").grid(row=2, column=0, sticky="w")
        ttk.Spinbox(frm4, from_=0.1, to=0.99, increment=0.01, textvariable=self.q_strong, width=6).grid(row=2, column=1, sticky="w")

        frm5 = ttk.LabelFrame(parent, text="Lexicon matching", padding=8)
        frm5.pack(fill="x", pady=6)
        ttk.Checkbutton(frm5, text="Fuzzy lexicon (RapidFuzz)", variable=self.fuzzy_lexicon).grid(row=0, column=0, sticky="w")
        ttk.Label(frm5, text="Fuzzy thr:").grid(row=0, column=1, sticky="w")
        ttk.Spinbox(frm5, from_=60, to=98, increment=1, textvariable=self.fuzzy_thr, width=6).grid(row=0, column=2, sticky="w")
        ttk.Label(frm5, text=f"rapidfuzz={'OK' if RAPIDFUZZ_OK else 'NOT INSTALLED'}", foreground="#555").grid(row=1, column=0, columnspan=3, sticky="w")




        frm_story = ttk.LabelFrame(parent, text="Narrative filter (story vs innovation)", padding=8)
        frm_story.pack(fill="x", pady=6)
        ttk.Checkbutton(frm_story, text="Filter narrative-heavy chunks", variable=self.story_filter_on).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(frm_story, text="Story prob thr:").grid(row=1, column=0, sticky="w")
        ttk.Spinbox(frm_story, from_=0.50, to=0.99, increment=0.01, textvariable=self.story_prob_threshold, width=6).grid(row=1, column=1, sticky="w")
        ttk.Label(frm_story, text="Penalty:").grid(row=2, column=0, sticky="w")
        ttk.Spinbox(frm_story, from_=0.00, to=0.30, increment=0.01, textvariable=self.story_penalty, width=6).grid(row=2, column=1, sticky="w")
        ttk.Label(frm_story, text="(If enabled: subtract story_prob × penalty; and drop rows with story_prob ≥ thr and no innovation markers.)", foreground="#555", wraplength=340).grid(row=3, column=0, columnspan=3, sticky="w", pady=(4,0))

        frm6 = ttk.LabelFrame(parent, text="Computed thresholds (after run)", padding=8)
        frm6.pack(fill="x", pady=6)
        self.lbl_thr = ttk.Label(frm6, text="t_weak=-  |  t_emerging=-  |  t_strong=-", foreground="#333")
        self.lbl_thr.pack(anchor="w")

        tip = ttk.Label(
            parent,
            text="Tip: click a row → the context will be highlighted to show where the signal comes from + a full explanation (why strong/emerging/weak).",
            foreground="#555",
            wraplength=360
        )
        tip.pack(anchor="w", pady=(10,0))

    def _build_signals_tab(self, parent):
        pan = ttk.Panedwindow(parent, orient="vertical")
        pan.pack(fill="both", expand=True)

        table_fr = ttk.Frame(pan)
        pan.add(table_fr, weight=3)

        cols = ["rank","score","strength","practice@location","location","practice","problem","impact","actor","cluster"]
        self.tree = ttk.Treeview(table_fr, columns=cols, show="headings", height=14)
        for c in cols:
            self.tree.heading(c, text=c)

        self.tree.column("rank", width=60, anchor="e")
        self.tree.column("score", width=80, anchor="e")
        self.tree.column("strength", width=90, anchor="center")
        self.tree.column("practice@location", width=390)
        self.tree.column("location", width=160)
        self.tree.column("practice", width=240)
        self.tree.column("problem", width=240)
        self.tree.column("impact", width=240)
        self.tree.column("actor", width=170)
        self.tree.column("cluster", width=80, anchor="center")

        yscroll = ttk.Scrollbar(table_fr, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.on_select_row)

        details_fr = ttk.Frame(pan)
        pan.add(details_fr, weight=2)

        split = ttk.Panedwindow(details_fr, orient="horizontal")
        split.pack(fill="both", expand=True)

        # Left: highlighted context + explanation
        left = ttk.Frame(split, padding=6)
        split.add(left, weight=3)

        self.txt = tk.Text(left, wrap="word", height=18)
        self.txt.pack(fill="both", expand=True)

        # Highlight tag styles
        self.txt.tag_configure("HL_ACTOR", background="#fff2cc")      # yellow
        self.txt.tag_configure("HL_PRACTICE", background="#d9ead3")   # green
        self.txt.tag_configure("HL_PROBLEM", background="#f4cccc")    # red
        self.txt.tag_configure("HL_IMPACT", background="#cfe2f3")     # blue
        self.txt.tag_configure("HL_LOC", background="#ead1dc")        # purple
        self.txt.tag_configure("HL_BOLD", font=("TkDefaultFont", 10, "bold"))
        self.txt.tag_configure("HL_DIM", foreground="#555")

        # Right: template + breakdown
        right = ttk.Frame(split, padding=6)
        split.add(right, weight=2)

        box_t = ttk.LabelFrame(right, text="Signal Template", padding=8)
        box_t.pack(fill="x", pady=(0,6))
        self.lbl_strength = ttk.Label(box_t, text="Strength: -   |   Final: -", font=("Arial", 11, "bold"))
        self.lbl_strength.pack(anchor="w")
        self.lbl_template = ttk.Label(box_t, text="Actor | Practice | Location | Problem | Impact", wraplength=520)
        self.lbl_template.pack(anchor="w", pady=(6,0))
        self.lbl_why_short = ttk.Label(box_t, text="Why (short): -", wraplength=520, foreground="#444")
        self.lbl_why_short.pack(anchor="w", pady=(4,0))

        box_s = ttk.LabelFrame(right, text="Slots + Lexicon hits", padding=8)
        box_s.pack(fill="x", pady=6)
        self.slot_vars: Dict[str, tk.StringVar] = {}
        for name in ["actor","practice_or_tech","location","problem","impact_or_evidence"]:
            v = tk.StringVar(value=f"{name}: -")
            self.slot_vars[name] = v
            ttk.Label(box_s, textvariable=v, wraplength=520).pack(anchor="w", pady=2)

        self.lex_hits = tk.StringVar(value="Lex hits: -")
        ttk.Label(box_s, textvariable=self.lex_hits, wraplength=520, foreground="#555").pack(anchor="w", pady=(6,0))

        box_b = ttk.LabelFrame(right, text="Score breakdown", padding=8)
        box_b.pack(fill="x", pady=6)

        self.bar_vars: Dict[str, tk.DoubleVar] = {}
        self.bar_lbls: Dict[str, ttk.Label] = {}
        for key in ["semantic_relevance","structural_score","deviation_score","intent_score","problem_solution_score","evidence_score","diffusion_score","geo_score"]:
            row = ttk.Frame(box_b)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=key, width=22).pack(side="left")
            v = tk.DoubleVar(value=0.0)
            self.bar_vars[key] = v
            ttk.Progressbar(row, variable=v, maximum=1.0).pack(side="left", fill="x", expand=True, padx=6)
            lbl = ttk.Label(row, text="0.00", width=6, anchor="e")
            lbl.pack(side="right")
            self.bar_lbls[key] = lbl

        self.txt.insert(
            "end",
            "Run mining, then click a row to see:\n"
            "- highlighted context\n"
            "- score breakdown\n"
            "- explanation why strong/emerging/weak/noise.\n"
        )

    def _build_hotspots_tab(self, parent):
        cols = ["location","practice_or_tech","count"]
        self.hot_tree = ttk.Treeview(parent, columns=cols, show="headings", height=20)
        for c in cols:
            self.hot_tree.heading(c, text=c)
        self.hot_tree.column("location", width=260)
        self.hot_tree.column("practice_or_tech", width=900)
        self.hot_tree.column("count", width=90, anchor="e")

        yscroll = ttk.Scrollbar(parent, orient="vertical", command=self.hot_tree.yview)
        self.hot_tree.configure(yscrollcommand=yscroll.set)
        self.hot_tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")

    def _build_topic_tab(self, parent):
        cols = ["cluster_id","signal_strength","count"]
        self.topic_tree = ttk.Treeview(parent, columns=cols, show="headings", height=20)
        for c in cols:
            self.topic_tree.heading(c, text=c)
        self.topic_tree.column("cluster_id", width=120, anchor="center")
        self.topic_tree.column("signal_strength", width=160, anchor="center")
        self.topic_tree.column("count", width=120, anchor="e")

        yscroll = ttk.Scrollbar(parent, orient="vertical", command=self.topic_tree.yview)
        self.topic_tree.configure(yscrollcommand=yscroll.set)
        self.topic_tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")


    # ---------- Timeline tab ----------
    def _build_timeline_tab(self, parent):
        """Plot signal evolution over time (requires a date/timestamp column in the input Excel)."""
        top = ttk.Frame(parent, padding=10)
        top.pack(fill="x")

        self.timeline_mode = tk.StringVar(value="count_strong_emerging")
        ttk.Label(top, text="Metric:").pack(side="left")
        ttk.Combobox(
            top, textvariable=self.timeline_mode,
            values=["count_strong_emerging", "avg_final_score"],
            width=22, state="readonly"
        ).pack(side="left", padx=6)

        ttk.Label(top, text="Group by:").pack(side="left", padx=(10,0))
        self.timeline_group = tk.StringVar(value="cluster_id")
        ttk.Combobox(
            top, textvariable=self.timeline_group,
            values=["cluster_id", "practice_or_tech", "practice_at_location"],
            width=22, state="readonly"
        ).pack(side="left", padx=6)

        ttk.Button(top, text="Update plot", command=self._update_timeline_plot).pack(side="left", padx=(10,0))

        ttk.Label(
            parent,
            text="Note: Timeline needs a date/timestamp column in the input Excel (e.g., date/Date/timestamp/created_at).",
            foreground="#555"
        ).pack(anchor="w", padx=10, pady=(0,6))

        self.timeline_canvas_container = ttk.Frame(parent)
        self.timeline_canvas_container.pack(fill="both", expand=True, padx=10, pady=10)

        self._timeline_canvas = None
        self._timeline_fig = None

    def _update_timeline_plot(self):
        if getattr(self, "last_results_df", None) is None or len(self.last_results_df) == 0:
            messagebox.showinfo("Timeline", "No results yet. Run Mining first.")
            return

        df = self.last_results_df.copy()
        if "date" not in df.columns or df["date"].isna().all():
            messagebox.showwarning(
                "Timeline",
                "No date/timestamp column detected in input. Add a date column (YYYY-MM-DD) to plot a timeline."
            )
            return

        dt = pd.to_datetime(df["date"], errors="coerce")
        df = df[~dt.isna()].copy()
        df["dt"] = pd.to_datetime(df["date"], errors="coerce")
        df = df[~df["dt"].isna()].copy()
        if len(df) == 0:
            messagebox.showwarning(
                "Timeline",
                "Date column exists but cannot be parsed. Use ISO dates (YYYY-MM-DD) or a standard timestamp."
            )
            return

        df["month"] = df["dt"].dt.to_period("M").dt.to_timestamp()

        group_key = self.timeline_group.get()
        if group_key not in df.columns:
            group_key = "cluster_id"

        metric = self.timeline_mode.get()
        if metric == "count_strong_emerging":
            df2 = df[df["signal_strength"].isin(["strong", "emerging"])].copy()
            agg = df2.groupby(["month", group_key]).size().reset_index(name="value")
        else:
            agg = df.groupby(["month", group_key])["final_signal_score"].mean().reset_index(name="value")

        totals = agg.groupby(group_key)["value"].sum().sort_values(ascending=False)
        top_groups = list(totals.head(5).index)
        agg = agg[agg[group_key].isin(top_groups)]

        fig = Figure(figsize=(7.5, 4.2), dpi=100)
        ax = fig.add_subplot(111)
        for gname in top_groups:
            sub = agg[agg[group_key] == gname].sort_values("month")
            ax.plot(sub["month"].values, sub["value"].values, label=str(gname))

        ax.set_title("Signal timeline (top groups)")
        ax.set_xlabel("Month")
        ax.set_ylabel("Count (strong+emerging)" if metric == "count_strong_emerging" else "Avg final_score")
        ax.legend(loc="upper left", fontsize=8)
        fig.autofmt_xdate(rotation=30)

        for child in self.timeline_canvas_container.winfo_children():
            child.destroy()
        canvas = FigureCanvasTkAgg(fig, master=self.timeline_canvas_container)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

        self._timeline_canvas = canvas
        self._timeline_fig = fig

    # ---------- Customize tab ----------
    def _build_customize_tab(self, parent):
        wrap = ttk.Panedwindow(parent, orient="horizontal")
        wrap.pack(fill="both", expand=True, padx=6, pady=6)

        left = ttk.Frame(wrap, padding=8)
        wrap.add(left, weight=1)

        ttk.Label(left, text="Gazetteer (one per line)", font=("Arial", 11, "bold")).pack(anchor="w")
        self.txt_gaz = tk.Text(left, wrap="word", height=22)
        self.txt_gaz.pack(fill="both", expand=True)
        self.txt_gaz.insert("1.0", "\n".join(self.custom_gazetteer))

        right = ttk.Frame(wrap, padding=8)
        wrap.add(right, weight=1)

        lexfrm = ttk.LabelFrame(right, text="Lexicon JSON (actor/practice/problem/impact/context)", padding=6)
        lexfrm.pack(fill="both", expand=True)
        self.txt_lex = tk.Text(lexfrm, wrap="word", height=14)
        self.txt_lex.pack(fill="both", expand=True)
        self.txt_lex.insert("1.0", json.dumps(self.custom_lexicon, ensure_ascii=False, indent=2))

        tplfrm = ttk.LabelFrame(right, text="Template Spec JSON (dynamic template)", padding=6)
        tplfrm.pack(fill="both", expand=True, pady=(8,0))
        self.txt_tpl = tk.Text(tplfrm, wrap="word", height=8)
        self.txt_tpl.pack(fill="both", expand=True)
        self.txt_tpl.insert("1.0", json.dumps(self.custom_template_spec, ensure_ascii=False, indent=2))

        bottom = ttk.Frame(parent, padding=8)
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Save config JSON", command=self.on_save_custom).pack(side="left")
        ttk.Button(bottom, text="Load config JSON", command=self.on_load_custom).pack(side="left", padx=8)
        ttk.Button(bottom, text="Reset defaults", command=self.on_reset_custom).pack(side="left", padx=8)

    # ---------- helpers ----------
    def update_progress(self, p: float, msg: str):
        def _ui():
            self.progress.set(float(p))
            self.status.set(msg)
        self.root.after(0, _ui)

    def _clear_highlights(self):
        for tag in ["HL_ACTOR","HL_PRACTICE","HL_PROBLEM","HL_IMPACT","HL_LOC","HL_BOLD","HL_DIM"]:
            self.txt.tag_remove(tag, "1.0", "end")

    def _clear_detail_panels(self):
        self.lbl_strength.config(text="Strength: -   |   Final: -")
        self.lbl_template.config(text="Actor | Practice | Location | Problem | Impact")
        self.lbl_why_short.config(text="Why (short): -")
        for k in self.slot_vars:
            self.slot_vars[k].set(f"{k}: -")
        self.lex_hits.set("Lex hits: -")
        for k, v in self.bar_vars.items():
            v.set(0.0)
            self.bar_lbls[k].config(text="0.00")

    def _apply_highlights_and_text(self, r: pd.Series):
        """Show context + explanation, and highlight extracted slots in the context."""
        self._clear_highlights()

        ctx = _norm(r.get("context_text",""))
        actor = _norm(r.get("actor",""))
        practice = _norm(r.get("practice_or_tech",""))
        problem = _norm(r.get("problem",""))
        impact = _norm(r.get("impact_or_evidence",""))
        loc = _norm(r.get("location",""))

        thr = self.thresholds
        q = {"q_weak": float(self.q_weak.get()), "q_emerging": float(self.q_emerging.get()), "q_strong": float(self.q_strong.get())}
        explain_long = build_strength_explanation(r, thr=thr, q=q)

        self.txt.delete("1.0", "end")
        self.txt.insert("end", "CONTEXT (highlighted)\n", ("HL_BOLD",))
        self.txt.insert("end", ctx + "\n\n")

        self.txt.insert("end", "EXPLANATION (why strong/emerging/weak/noise)\n", ("HL_BOLD",))
        self.txt.insert("end", explain_long + "\n\n", ("HL_DIM",))

        self.txt.insert("end", "LEGEND\n", ("HL_BOLD",))
        self.txt.insert("end", "Actor  ", ("HL_ACTOR",))
        self.txt.insert("end", "Practice  ", ("HL_PRACTICE",))
        self.txt.insert("end", "Problem  ", ("HL_PROBLEM",))
        self.txt.insert("end", "Impact  ", ("HL_IMPACT",))
        self.txt.insert("end", "Location\n", ("HL_LOC",))

        full_text = self.txt.get("1.0", "end-1c")
        ctx_start = full_text.find(ctx)
        if ctx_start < 0 or not ctx:
            return

        def highlight_phrase(phrase: str, tag: str):
            for a, b in _find_spans_in_text(ctx, phrase):
                start = _tk_index_from_charpos(ctx_start + a)
                end = _tk_index_from_charpos(ctx_start + b)
                self.txt.tag_add(tag, start, end)

        highlight_phrase(practice, "HL_PRACTICE")
        highlight_phrase(problem, "HL_PROBLEM")
        highlight_phrase(impact, "HL_IMPACT")
        highlight_phrase(actor, "HL_ACTOR")

        if loc and loc != "unspecified":
            for piece in [x.strip() for x in loc.split(";") if x.strip()]:
                highlight_phrase(piece, "HL_LOC")

    # ---------- config handlers ----------
    def on_save_custom(self):
        try:
            gaz = [x.strip() for x in self.txt_gaz.get("1.0","end").splitlines() if x.strip()]
            lex = json.loads(self.txt_lex.get("1.0","end"))
            tpl = json.loads(self.txt_tpl.get("1.0","end"))
        except Exception as e:
            messagebox.showerror("Save config", f"Invalid JSON / text:\n{e}")
            return

        self.custom_gazetteer = _unique_keep_order(gaz)
        self.custom_lexicon = {k: _unique_keep_order(list(lex.get(k, []))) for k in ["actor","practice","problem","impact","context"]}
        self.custom_template_spec = tpl

        save_custom_config({"gazetteer": self.custom_gazetteer, "lexicon": self.custom_lexicon, "template_spec": self.custom_template_spec})
        messagebox.showinfo("Save config", "Saved to agri_custom_config_tk_ctx.json")

    def on_load_custom(self):
        cfg = load_custom_config()
        if not cfg:
            messagebox.showwarning("Load config", "No config file found (agri_custom_config_tk_ctx.json).")
            return
        self.custom_gazetteer = _unique_keep_order(cfg.get("gazetteer", DEFAULT_GAZETTEER))
        self.custom_lexicon = cfg.get("lexicon", DEFAULT_LEXICON)
        self.custom_lexicon = {k: _unique_keep_order(list(self.custom_lexicon.get(k, []))) for k in ["actor","practice","problem","impact","context"]}
        self.custom_template_spec = cfg.get("template_spec", DEFAULT_TEMPLATE_SPEC)

        # refresh editors if they exist
        if hasattr(self, "txt_gaz"):
            self.txt_gaz.delete("1.0","end"); self.txt_gaz.insert("1.0","\n".join(self.custom_gazetteer))
        if hasattr(self, "txt_lex"):
            self.txt_lex.delete("1.0","end"); self.txt_lex.insert("1.0", json.dumps(self.custom_lexicon, ensure_ascii=False, indent=2))
        if hasattr(self, "txt_tpl"):
            self.txt_tpl.delete("1.0","end"); self.txt_tpl.insert("1.0", json.dumps(self.custom_template_spec, ensure_ascii=False, indent=2))

        messagebox.showinfo("Load config", "Loaded custom config.")

    def on_reset_custom(self):
        self.custom_gazetteer = list(DEFAULT_GAZETTEER)
        self.custom_lexicon = {k: list(DEFAULT_LEXICON.get(k, [])) for k in ["actor","practice","problem","impact","context"]}
        self.custom_template_spec = dict(DEFAULT_TEMPLATE_SPEC)

        if hasattr(self, "txt_gaz"):
            self.txt_gaz.delete("1.0","end"); self.txt_gaz.insert("1.0","\n".join(self.custom_gazetteer))
        if hasattr(self, "txt_lex"):
            self.txt_lex.delete("1.0","end"); self.txt_lex.insert("1.0", json.dumps(self.custom_lexicon, ensure_ascii=False, indent=2))
        if hasattr(self, "txt_tpl"):
            self.txt_tpl.delete("1.0","end"); self.txt_tpl.insert("1.0", json.dumps(self.custom_template_spec, ensure_ascii=False, indent=2))

        save_custom_config({"gazetteer": self.custom_gazetteer, "lexicon": self.custom_lexicon, "template_spec": self.custom_template_spec})
        messagebox.showinfo("Reset", "Reset to defaults.")

    # ---------- run + refresh ----------
    def on_run(self):
        if not self.input_path.get().strip():
            messagebox.showwarning("Run Mining", "Please select an input Excel file.")
            return

        self.status.set("Running...")
        self.progress.set(0.0)
        self._clear_detail_panels()

        def worker():
            try:
                extra = {
                    "story_filter_on": bool(self.story_filter_on.get()),
                    "story_prob_threshold": float(self.story_prob_threshold.get()),
                    "story_penalty": float(self.story_penalty.get()),
                }
                out_df, hot_df, topic_df, thr = run_mining_context_first(
                    input_xlsx=self.input_path.get().strip(),
                    bi_encoder=self.bi_encoder.get().strip(),
                    use_cross=bool(self.use_cross.get()),
                    cross_encoder=self.cross_encoder.get().strip(),
                    topk_retrieve=int(self.topk_retrieve.get()),
                    topk_rerank=int(self.topk_rerank.get()),
                    apply_dedup=bool(self.apply_dedup.get()),
                    dedup_thr=float(self.dedup_thr.get()),
                    cluster_signals=bool(self.cluster_signals.get()),
                    n_clusters=int(self.n_clusters.get()),
                    q_weak=float(self.q_weak.get()),
                    q_emerging=float(self.q_emerging.get()),
                    q_strong=float(self.q_strong.get()),
                    fuzzy_lexicon=bool(self.fuzzy_lexicon.get()),
                    fuzzy_thr=int(self.fuzzy_thr.get()),
                    lexicon=self.custom_lexicon,
                    gazetteer=self.custom_gazetteer,
                    template_spec=self.custom_template_spec,
                    extra_config=extra,
                    progress_cb=self.update_progress
                )

                def ui_done():
                    self.df_full = out_df
                    self.df_hotspots = hot_df
                    self.df_topic = topic_df
                    self.thresholds = thr
                    self.last_results_df = out_df

                    self.lbl_thr.config(text=f"t_weak={thr['t_weak']:.3f}  |  t_emerging={thr['t_emerging']:.3f}  |  t_strong={thr['t_strong']:.3f}")
                    self.refresh_all_views()
                    self.update_progress(1.0, "Done. Click a row to see highlight + explanation.")
                self.root.after(0, ui_done)

            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Run Mining", str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def refresh_all_views(self):
        self.refresh_table()
        self.refresh_hotspots()
        self.refresh_topic()

    def refresh_table(self):
        for x in self.tree.get_children():
            self.tree.delete(x)
        if self.df_full is None or len(self.df_full) == 0:
            return
        df = self.df_full.copy().reset_index(drop=True)
        df["rank"] = np.arange(1, len(df)+1)
        df["score"] = df["final_signal_score"].astype(float).round(3)
        df["strength"] = df["signal_strength"]
        df["practice@location"] = df["practice_at_location"]
        df["practice"] = df["practice_or_tech"]
        df["impact"] = df["impact_or_evidence"]
        df["cluster"] = df["cluster_id"]

        view_cols = ["rank","score","strength","practice@location","location","practice","problem","impact","actor","cluster"]
        self._table_view_df = df
        for i, row in df.iterrows():
            vals=[row.get(c,"") for c in view_cols]
            self.tree.insert("", "end", iid=str(i), values=vals)

    def refresh_hotspots(self):
        for x in self.hot_tree.get_children():
            self.hot_tree.delete(x)
        if self.df_hotspots is None or len(self.df_hotspots)==0:
            return
        for i, r in self.df_hotspots.iterrows():
            self.hot_tree.insert("", "end", values=[r.get("location",""), r.get("practice_or_tech",""), int(r.get("count",0))])

    def refresh_topic(self):
        for x in self.topic_tree.get_children():
            self.topic_tree.delete(x)
        if self.df_topic is None or len(self.df_topic)==0:
            return
        for i, r in self.df_topic.iterrows():
            self.topic_tree.insert("", "end", values=[r.get("cluster_id",""), r.get("signal_strength",""), int(r.get("count",0))])

    def on_select_row(self, event=None):
        if self._table_view_df is None:
            return
        sel = self.tree.selection()
        if not sel:
            return
        i = int(sel[0])
        r = self._table_view_df.iloc[i]

        # Update right panels
        strength = str(r.get("signal_strength","-")).upper()
        score = float(r.get("final_signal_score",0.0))
        self.lbl_strength.config(text=f"Strength: {strength}   |   Final: {score:.3f}")
        self.lbl_template.config(text=_norm(r.get("signal_template","unspecified")))
        self.lbl_why_short.config(text=f"Why (short): template ok, problem→impact, quantitative evidence (if present).")

        self.slot_vars["actor"].set(f"Actor: {_norm(r.get('actor',''))} (sim={float(r.get('actor_sim',0.0)):.2f})")
        self.slot_vars["practice_or_tech"].set(f"Practice: {_norm(r.get('practice_or_tech',''))} (sim={float(r.get('practice_sim',0.0)):.2f})")
        self.slot_vars["location"].set(f"Location: {_norm(r.get('location',''))}")
        self.slot_vars["problem"].set(f"Problem: {_norm(r.get('problem',''))} (sim={float(r.get('problem_sim',0.0)):.2f})")
        self.slot_vars["impact_or_evidence"].set(f"Impact: {_norm(r.get('impact_or_evidence',''))} (sim={float(r.get('impact_sim',0.0)):.2f})")

        self.lex_hits.set(
            "Lex hits: "
            f"actor[{_norm(r.get('lex_actor_hits',''))}], "
            f"practice[{_norm(r.get('lex_practice_hits',''))}], "
            f"problem[{_norm(r.get('lex_problem_hits',''))}], "
            f"impact[{_norm(r.get('lex_impact_hits',''))}]"
        )

        for key in self.bar_vars:
            v = float(r.get(key, 0.0))
            self.bar_vars[key].set(v)
            self.bar_lbls[key].config(text=f"{v:.2f}")

        self._apply_highlights_and_text(r)

    def on_export(self):
        if self.df_full is None or len(self.df_full) == 0:
            messagebox.showinfo("Export", "No results to export. Run Mining first.")
            return
        out_path = self.output_path.get().strip() or "agri_signals_export.xlsx"
        try:
            self.df_full.to_excel(out_path, index=False)
            messagebox.showinfo("Export", f"Exported to:\n{out_path}")
        except Exception as e:
            messagebox.showerror("Export", str(e))

def main():
    root = tk.Tk()
    try:
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")
    except Exception:
        pass
    AgriSignalMinerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()