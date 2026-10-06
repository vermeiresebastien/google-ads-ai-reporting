from gads_analytics.council import aggregate_rankings, parse_ranking


def test_parse_ranking_reads_the_final_list():
    text = "Response A is thin.\n\nFINAL RANKING:\n1. Response C\n2. Response A\n3. Response B"
    assert parse_ranking(text) == ["Response C", "Response A", "Response B"]


def test_aggregate_rankings_averages_positions():
    label_to_model = {"Response A": "openai/a", "Response B": "google/b"}
    rankings = [
        {"ranking": "FINAL RANKING:\n1. Response B\n2. Response A"},
        {"ranking": "FINAL RANKING:\n1. Response B\n2. Response A"},
    ]
    aggregate = aggregate_rankings(rankings, label_to_model)
    assert aggregate[0] == {"model": "google/b", "average_rank": 1.0}
    assert aggregate[1]["model"] == "openai/a"
