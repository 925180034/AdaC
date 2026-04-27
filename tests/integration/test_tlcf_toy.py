from __future__ import annotations


def test_tlcf_toy_known_join_reaches_top_ranking() -> None:
    from adacascade.agents.retrieval.aggregate import aggregate
    from adacascade.agents.retrieval.layer2 import intersect_c2
    from adacascade.agents.retrieval.layer3 import _merge_scores

    c1 = [
        {"table_id": "orders", "s1": 0.91},
        {"table_id": "products", "s1": 0.64},
        {"table_id": "weather", "s1": 0.42},
    ]
    qdrant_ids = {"orders", "products", "unrelated"}
    qdrant_scores = {"orders": 0.93, "products": 0.68, "unrelated": 0.99}
    c2 = intersect_c2(c1, qdrant_ids, qdrant_scores, theta_2=0.55)
    assert {item["table_id"] for item in c2} == {"orders", "products"}

    llm_scores = {
        idx: 0.94 if item["table_id"] == "orders" else 0.51
        for idx, item in enumerate(c2, start=1)
    }
    c3 = _merge_scores(c2, llm_scores, theta_3=0.50)
    ranking = aggregate(c3, weights={"w1": 0.3, "w2": 0.3, "w3": 0.4})

    assert {item["table_id"] for item in c3} == {"orders", "products"}
    assert ranking[0]["table_id"] == "orders"
    assert ranking[0]["layer_scores"] == {"s1": 0.91, "s2": 0.93, "s3": 0.94}
