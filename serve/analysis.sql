-- Market-analysis queries powering the Metabase dashboard.
-- Also runnable directly: sqlite3 data.db < analysis.sql

-- 1. Top products by estimated revenue (price * cumulative sold) — the headline "what sells".
SELECT name, category, price, sold_count, est_revenue, rating, seller_name
FROM products ORDER BY est_revenue DESC LIMIT 50;

-- 2. Best categories — total est revenue, units, avg price.
SELECT category,
       SUM(est_revenue) AS total_revenue,
       SUM(sold_count)  AS units_sold,
       ROUND(AVG(price)) AS avg_price,
       COUNT(*)         AS listings
FROM products GROUP BY category ORDER BY total_revenue DESC;

-- 3. Seller concentration — low distinct sellers = low competition = opportunity.
SELECT category,
       COUNT(DISTINCT seller_id) AS distinct_sellers,
       COUNT(*)                  AS listings,
       ROUND(1.0 * COUNT(*) / COUNT(DISTINCT seller_id), 1) AS listings_per_seller
FROM products GROUP BY category ORDER BY distinct_sellers ASC;

-- 4. Price vs demand — which price bands actually move volume (scatter x=price y=sold).
SELECT price, sold_count, category
FROM products WHERE price > 0 AND sold_count > 0;

-- 5. Demand gaps — high sales BUT low rating: unmet demand you could serve better.
SELECT name, category, sold_count, rating, review_count, price
FROM products WHERE rating > 0 AND rating < 4.3 AND sold_count >= 1000
ORDER BY sold_count DESC LIMIT 30;

-- 6. Top sellers — who dominates, by revenue and breadth.
SELECT seller_name,
       COUNT(*)         AS products,
       SUM(est_revenue) AS revenue,
       SUM(sold_count)  AS units_sold
FROM products GROUP BY seller_name ORDER BY revenue DESC LIMIT 25;
