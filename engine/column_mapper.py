import re
from typing import Dict, List, Optional, Tuple
from rapidfuzz import process, fuzz
from config import FUZZY_MATCH_THRESHOLD

# Internal Standard Schema Field Definitions
INTERNAL_FIELDS = {
    "sin": {
        "label": "SIN",
        "required": True,
        "aliases": ["sin", "student identification number", "student identification no", "student id", "student_id", "usn"]
    },
    "full_name": {
        "label": "STUDENT FULL NAME",
        "required": True,
        "aliases": ["student full name", "student name", "full name", "candidate name", "name"]
    },
    "program": {
        "label": "PROGRAM",
        "required": True,
        "aliases": ["program", "degree", "course", "program name"]
    },
    "gender": {
        "label": "GENDER",
        "required": False,
        "aliases": ["gender", "sex", "m/f", "m f", "gender (m/f)"]
    }
}

class ColumnMapper:
    """Intelligently matches arbitrary Excel header columns to internal standard schema fields."""

    @classmethod
    def map_columns(cls, raw_headers: List[str]) -> Tuple[Dict[str, str], List[str], List[str]]:
        """
        Maps raw column names to internal standard field names.
        Returns:
            - mapping: Dict[raw_header, internal_field_key]
            - unmapped_headers: List[raw_header]
            - missing_required: List[internal_field_key]
        """
        mapping: Dict[str, str] = {}
        mapped_internal: set = set()
        
        # Cleaned headers list
        cleaned_headers = [str(h).strip() for h in raw_headers if str(h).strip()]

        for raw in cleaned_headers:
            norm_raw = cls._normalize_text(raw)
            best_match_key = None
            best_score = 0.0

            for key, meta in INTERNAL_FIELDS.items():
                if key in mapped_internal:
                    continue

                # Exact or Alias matching
                for alias in meta["aliases"]:
                    if norm_raw == alias:
                        best_match_key = key
                        best_score = 100.0
                        break
                
                if best_score < 100.0:
                    # Fuzzy match against aliases
                    match = process.extractOne(
                        norm_raw,
                        meta["aliases"],
                        scorer=fuzz.token_sort_ratio
                    )
                    if match and match[1] > best_score and match[1] >= FUZZY_MATCH_THRESHOLD:
                        best_score = match[1]
                        best_match_key = key

            if best_match_key:
                mapping[raw] = best_match_key
                mapped_internal.add(best_match_key)

        unmapped = [h for h in raw_headers if h not in mapping]
        
        # Check missing required fields
        missing_required = []
        for key, meta in INTERNAL_FIELDS.items():
            if meta["required"] and key not in mapped_internal:
                missing_required.append(meta["label"])

        return mapping, unmapped, missing_required

    @staticmethod
    def _normalize_text(text: str) -> str:
        text = text.lower().strip()
        text = re.sub(r'[_\-\/\:\.]', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text
