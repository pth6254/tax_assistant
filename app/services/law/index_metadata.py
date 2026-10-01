"""Vector lineage describes actual embedding inputs, never legal approval."""
import math

import config
from app.services.evidence import digest

INDEX_VERSION = 'law-index-20260930-v1'


def validate_vectors(vectors, expected):
    if vectors is None:
        return
    if len(vectors) != expected:
        raise ValueError('embedding_count_mismatch')
    for vector in vectors:
        if (len(vector) != config.EMBED_DIM or not all(math.isfinite(float(v)) for v in vector)
                or not any(float(v) != 0 for v in vector)):
            raise ValueError('invalid_embedding_vector')


def vector_metadata(source_text, input_text, *, v1=True, v2=False, source_id='', run_id=''):
    result = {'source_hash': digest(source_text), 'index_version': INDEX_VERSION,
              'input_hash': digest(input_text)}
    for version, written in (('v1', v1), ('v2', v2)):
        if not written:
            continue
        dual = config.EMBEDDING_DUAL_WRITE
        result[version] = {
            'provider': getattr(config, f'EMBEDDING_{version.upper()}_PROVIDER') if dual else config.EMBEDDING_PROVIDER,
            'model': getattr(config, f'EMBEDDING_{version.upper()}_MODEL') if dual else config.EMBEDDING_MODEL,
            'dimension': config.EMBED_DIM,
            'input_hash': digest(input_text),
        }
    if source_id:
        result['snapshot_source_id'] = source_id
    if run_id:
        result['repair_run_id'] = run_id
    return result
