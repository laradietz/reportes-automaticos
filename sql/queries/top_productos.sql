-- Top 15 productos con ranking y % acumulado (análisis de Pareto 80/20).
WITH p AS (
    SELECT pr.id_producto, pr.nombre, pr.categoria,
           SUM(v.cantidad)                AS unidades,
           ROUND(SUM(v.importe_neto), 2)  AS ventas_netas
    FROM fact_ventas v JOIN dim_producto pr ON pr.id_producto = v.id_producto
    GROUP BY pr.id_producto, pr.nombre, pr.categoria
),
r AS (
    SELECT *,
           RANK() OVER (ORDER BY ventas_netas DESC) AS ranking,
           ROUND(100.0 * SUM(ventas_netas) OVER (ORDER BY ventas_netas DESC ROWS UNBOUNDED PRECEDING)
                 / SUM(ventas_netas) OVER (), 1) AS acumulado_pct
    FROM p
)
SELECT ranking, nombre, categoria, unidades, ventas_netas, acumulado_pct
FROM r
WHERE ranking <= 15
ORDER BY ranking;
