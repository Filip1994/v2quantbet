from h2h.api.dashboard import _production_bucket_links_html
from h2h.corner_buckets import CORNER_OPERATIONS_BUCKETS


def test_all_selected_corner_links_open_exact_research_cube():
    for bucket in CORNER_OPERATIONS_BUCKETS:
        html = _production_bucket_links_html([bucket.bucket_id])
        assert 'https://quantbet-research-production.up.railway.app/research/analytics/corners?' in html
        assert 'bucket_id=' + bucket.bucket_id in html
        assert '#operations-corner-buckets' in html
        assert 'quantbet-quantlab-production' not in html


def test_historical_bucket_labels_survive_without_retired_service_dependency():
    from h2h.production_buckets import CORNER_OVER_GAP_1_2_ODDS_1_61_1_80, GOALLAB_OU_OVER_XG_2_5_3_0
    html = _production_bucket_links_html([CORNER_OVER_GAP_1_2_ODDS_1_61_1_80,GOALLAB_OU_OVER_XG_2_5_3_0])
    assert 'quantbet-quantlab-production' not in html
    assert '/research/analytics/corners' in html
    assert 'Archived GoalLab bucket' in html
