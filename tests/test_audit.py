from pipeline.audit import compare_page


def test_compare_page():
    db_rows = {"1": (100.0, 2700), "2": (50.0, 10)}
    live = [{"nid": "1", "price": "100", "itemSoldCntShow": "2.7K sold"},
            {"nid": "2", "price": "55", "itemSoldCntShow": "10 sold"},
            {"nid": "9", "price": "1"}]           # not in DB -> ignored
    assert compare_page(db_rows, live) == (2, 1, 2)  # checked, price matches, sold matches
