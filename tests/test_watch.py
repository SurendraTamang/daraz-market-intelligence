from watch import movers


def test_movers_weekly_delta_and_price_change():
    now = [{"nid": "a", "name": "A", "sold": 2800, "price": 150.0, "seller": "s1"},
           {"nid": "b", "name": "B", "sold": 40, "price": 199.0, "seller": "s2"}]       # new listing
    before = [{"nid": "a", "name": "A", "sold": 2700, "price": 160.0, "seller": "s1"}]
    rows = {r["nid"]: r for r in movers(now, before, days=7)}
    assert rows["a"]["per_week"] == 100 and rows["a"]["price_change"] == -10.0
    assert rows["b"]["per_week"] is None and rows["b"]["new"] is True


def test_movers_scales_to_a_week():
    rows = movers([{"nid": "a", "name": "A", "sold": 130, "price": 1.0, "seller": "s"}],
                  [{"nid": "a", "name": "A", "sold": 100, "price": 1.0, "seller": "s"}], days=3)
    assert rows[0]["per_week"] == 70


def test_niche_change_is_like_for_like():
    from watch import niche_change
    before = [{"nid": "a", "sold": 100, "seller": "s1", "page": 1}]
    now = [{"nid": "a", "sold": 130, "seller": "s1", "page": 1},
           {"nid": "x", "sold": 5000, "seller": "s9", "page": 4}]     # deeper crawl today: not growth
    c = niche_change(now, before)
    assert c["units_change_matched"] == 30 and c["sellers_p1_change"] == 0 and c["new_on_p1"] == 0
