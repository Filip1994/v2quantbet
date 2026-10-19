from h2h.api.dashboard import _production_bucket_links_html
from h2h.corner_buckets import CORNER_OPERATIONS_BUCKETS


def test_all_selected_corner_links_open_exact_research_cube():
    for bucket in CORNER_OPERATIONS_BUCKETS:
        html = _production_bucket_links_html([bucket.bucket_id])
        assert 'https://quantbet-research-production.up.railway.app/research/analytics/corners?' in html
        assert 'bucket_id=' + bucket.bucket_id in html
        assert '#operations-corner-buckets' in html
        assert 'quantbet-quantlab-production' not in html
