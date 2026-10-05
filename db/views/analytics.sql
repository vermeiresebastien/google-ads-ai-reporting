CREATE OR REPLACE VIEW account_performance_daily AS
SELECT
  account_id,
  date,
  SUM(impressions) AS impressions,
  SUM(clicks) AS clicks,
  SUM(cost) AS cost,
  SUM(conversions) AS conversions,
  SUM(conversion_value) AS conversion_value,
  CASE WHEN SUM(impressions) = 0 THEN NULL ELSE SUM(clicks)::numeric / SUM(impressions) END AS ctr,
  CASE WHEN SUM(clicks) = 0 THEN NULL ELSE SUM(cost) / SUM(clicks) END AS average_cpc,
  CASE WHEN SUM(impressions) = 0 THEN NULL ELSE SUM(cost) * 1000 / SUM(impressions) END AS average_cpm,
  CASE WHEN SUM(clicks) = 0 THEN NULL ELSE SUM(conversions) / SUM(clicks) END AS conversion_rate,
  CASE WHEN SUM(conversions) = 0 THEN NULL ELSE SUM(cost) / SUM(conversions) END AS cost_per_conversion,
  CASE WHEN SUM(cost) = 0 THEN NULL ELSE SUM(conversion_value) / SUM(cost) END AS roas
FROM campaign_daily
GROUP BY account_id, date;

CREATE OR REPLACE VIEW campaign_performance_daily AS
SELECT
  d.account_id,
  d.date,
  d.campaign_id,
  c.name AS campaign_name,
  c.status,
  c.advertising_channel_type,
  d.impressions,
  d.clicks,
  d.cost,
  d.conversions,
  d.conversion_value,
  d.ctr,
  d.average_cpc,
  d.conversion_rate,
  d.cost_per_conversion,
  d.roas,
  d.search_impression_share,
  d.search_budget_lost_impression_share,
  d.search_rank_lost_impression_share
FROM campaign_daily AS d
JOIN campaigns AS c ON c.id = d.campaign_id;

CREATE OR REPLACE VIEW keyword_performance_daily AS
SELECT
  d.account_id,
  d.date,
  d.keyword_id,
  d.campaign_id,
  d.ad_group_id,
  k.keyword_text,
  k.match_type,
  d.impressions,
  d.clicks,
  d.cost,
  d.conversions,
  d.conversion_value,
  d.ctr,
  d.average_cpc,
  d.conversion_rate,
  d.cost_per_conversion,
  d.roas,
  d.quality_score
FROM keyword_daily AS d
JOIN keywords AS k ON k.id = d.keyword_id;

CREATE OR REPLACE VIEW search_term_performance_daily AS
SELECT
  id,
  account_id,
  date,
  source,
  campaign_id,
  ad_group_id,
  search_term,
  keyword_id,
  keyword_resource,
  match_type,
  impressions,
  clicks,
  cost,
  conversions,
  conversion_value,
  ctr,
  average_cpc,
  conversion_rate,
  cost_per_conversion,
  roas
FROM search_terms_daily;

CREATE OR REPLACE VIEW recent_changes AS
SELECT
  id,
  account_id,
  resource_name,
  event_timestamp,
  resource_type,
  resource_changed_name,
  change_type,
  field_changed,
  old_value,
  new_value,
  client_type,
  user_email
FROM change_events;

CREATE OR REPLACE VIEW budget_opportunities AS
SELECT
  b.account_id,
  b.date,
  b.campaign_id,
  c.name AS campaign_name,
  b.budget,
  b.spend,
  b.budget_utilization,
  b.impressions,
  b.lost_impression_share_budget
FROM campaign_budget_daily AS b
JOIN campaigns AS c ON c.id = b.campaign_id
JOIN account_analytics_settings AS s ON s.account_id = b.account_id
WHERE b.lost_impression_share_budget >= s.budget_lost_is_min
  AND b.spend >= s.min_spend_for_anomaly;

CREATE OR REPLACE VIEW wasted_spend AS
SELECT
  t.account_id,
  t.date,
  t.search_term,
  t.campaign_id,
  t.cost,
  t.clicks,
  t.conversions
FROM search_terms_daily AS t
JOIN account_analytics_settings AS s ON s.account_id = t.account_id
WHERE t.conversions = 0
  AND t.cost >= s.zero_conversion_min_spend
  AND t.clicks >= s.min_clicks;

CREATE OR REPLACE VIEW performance_anomalies AS
SELECT
  d.account_id,
  d.date,
  SUM(d.cost) AS cost,
  SUM(d.conversions) AS conversions,
  SUM(d.conversion_value) AS conversion_value,
  CASE WHEN SUM(d.conversions) = 0 THEN NULL ELSE SUM(d.cost) / SUM(d.conversions) END AS cost_per_conversion,
  CASE WHEN SUM(d.cost) = 0 THEN NULL ELSE SUM(d.conversion_value) / SUM(d.cost) END AS roas
FROM campaign_daily AS d
GROUP BY d.account_id, d.date;

CREATE OR REPLACE FUNCTION campaign_period_comparison(
  p_account text,
  p_start date,
  p_end date,
  p_prev_start date,
  p_prev_end date
)
RETURNS TABLE (
  campaign_id text,
  campaign_name text,
  current_cost numeric,
  previous_cost numeric,
  current_conversions numeric,
  previous_conversions numeric,
  current_conversion_value numeric,
  previous_conversion_value numeric
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    c.id,
    c.name,
    COALESCE(cur.cost, 0),
    COALESCE(prev.cost, 0),
    COALESCE(cur.conversions, 0),
    COALESCE(prev.conversions, 0),
    COALESCE(cur.conversion_value, 0),
    COALESCE(prev.conversion_value, 0)
  FROM campaigns AS c
  LEFT JOIN (
    SELECT campaign_id, SUM(cost) AS cost, SUM(conversions) AS conversions, SUM(conversion_value) AS conversion_value
    FROM campaign_daily
    WHERE account_id = p_account AND date BETWEEN p_start AND p_end
    GROUP BY campaign_id
  ) AS cur ON cur.campaign_id = c.id
  LEFT JOIN (
    SELECT campaign_id, SUM(cost) AS cost, SUM(conversions) AS conversions, SUM(conversion_value) AS conversion_value
    FROM campaign_daily
    WHERE account_id = p_account AND date BETWEEN p_prev_start AND p_prev_end
    GROUP BY campaign_id
  ) AS prev ON prev.campaign_id = c.id
  WHERE c.account_id = p_account;
$$;
