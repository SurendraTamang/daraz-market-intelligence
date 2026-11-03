from pipeline.run import gate

GOOD = {"page1_total": 4900, "page1_failed": 40, "live": 4380, "best_live": 4389,
        "spot_checked": 150, "spot_price_ok": 149}


def test_gate_passes_a_healthy_run():
    assert gate(GOOD) == []


def test_gate_fails_on_blocks_coverage_or_spot_mismatch():
    assert "failed" in gate({**GOOD, "page1_failed": 400})[0]          # 8% > 5%
    assert "live categories" in gate({**GOOD, "live": 3000})[0]          # 68% < 90%
    assert "spot-check" in gate({**GOOD, "spot_price_ok": 100})[0]       # 67% < 90%


def test_gate_tolerates_first_run_and_no_spot_sample():
    assert gate({**GOOD, "best_live": 0, "spot_checked": 0, "spot_price_ok": 0}) == []


def test_crawl_complete_requires_coverage_and_few_failures():
    from pipeline.run import crawl_complete
    assert crawl_complete(live=4380, best=4389, failed=10, total=4900)
    assert not crawl_complete(live=751, best=4389, failed=97, total=919)     # this morning's run
    assert not crawl_complete(live=4380, best=4389, failed=300, total=4900)  # too many failures
    assert crawl_complete(live=4000, best=0, failed=0, total=4000)           # first run ever
