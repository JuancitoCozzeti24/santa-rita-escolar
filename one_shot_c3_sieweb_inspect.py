from __future__ import annotations

import inspect as pyinspect
import json
import unicodedata
from typing import Any

HEADERS = [135935, 135936, 135937, 135938]

def _norm(v: Any) -> str:
    t = unicodedata.normalize('NFD', str(v or ''))
    t = ''.join(ch for ch in t if unicodedata.category(ch) != 'Mn')
    return ' '.join(t.upper().split())

def inspect(classroom: Any, sieweb: Any) -> dict[str, Any]:
    print('C3_SIEWEB_SAVE_SIGNATURE=' + str(pyinspect.signature(sieweb.save_grades_verified)), flush=True)
    print('C3_SIEWEB_MULTI_SIGNATURE=' + str(pyinspect.signature(sieweb.save_grades_multi_verified)), flush=True)
    print('C3_SIEWEB_BUILD_RECORDS_SIGNATURE=' + str(pyinspect.signature(sieweb.build_grade_records)), flush=True)
    return {'queued':False,'course_name':'MATE 5TO - B','work':'C3: Evaluación semanal de matrices','count':0}
